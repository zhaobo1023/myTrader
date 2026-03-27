# Paper Trading 实盘验证系统 — 技术方案

**目标**：在 myTrader 现有基础上，新增一套模拟实盘追踪模块  
**核心价值**：消除回测的 look-ahead bias，用真实时序验证策略有效性  
**预计工期**：5~8 天（单人）

---

## 一、系统架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     Paper Trading System                     │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  信号生成层   │  持仓管理层  │  收益结算层  │   评估报告层   │
│  SignalGen   │  Position    │  Settlement  │   Evaluator    │
│              │  Manager     │  Engine      │                │
├──────────────┴──────────────┴──────────────┴────────────────┤
│                      数据存储层 (MySQL)                       │
│  pt_signals │ pt_positions │ pt_rounds │ pt_daily_prices   │
└─────────────────────────────────────────────────────────────┘
```

**文件结构**（放在 `strategist/paper_trading/`）：

```
strategist/paper_trading/
├── __init__.py
├── config.py            # 配置
├── signal_generator.py  # 信号生成（调用 XGBoost 策略）
├── position_manager.py  # 持仓记录管理
├── settlement.py        # 收益结算（T+1 买入 / T+N 卖出）
├── evaluator.py         # IC / ICIR / 超额收益计算
├── reporter.py          # 报告生成
├── scheduler.py         # 定时任务入口
├── run_paper_trading.py # 手动运行入口
└── README.md
```

---

## 二、数据库设计

### 表 1：`pt_rounds` — 每轮信号记录

```sql
CREATE TABLE pt_rounds (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    round_id      VARCHAR(32) NOT NULL UNIQUE,  -- 如 '20260328_CSI300'
    signal_date   DATE NOT NULL,                -- 信号生成日（周五）
    buy_date      DATE NOT NULL,                -- 买入日（signal_date + 1 交易日）
    sell_date     DATE NOT NULL,                -- 卖出日（buy_date + hold_days 交易日）
    index_name    VARCHAR(32) NOT NULL,         -- 指数池名称
    hold_days     INT DEFAULT 5,                -- 持仓天数（交易日）
    top_n         INT DEFAULT 10,               -- 选股数量
    status        ENUM('pending','active','settled','cancelled') DEFAULT 'pending',
    -- 结算后填充
    portfolio_ret DECIMAL(10,6) NULL,           -- 策略收益（扣费后，%）
    benchmark_ret DECIMAL(10,6) NULL,           -- 基准收益（%）
    excess_ret    DECIMAL(10,6) NULL,           -- 超额收益（%）
    ic            DECIMAL(10,6) NULL,           -- Spearman IC
    rank_ic       DECIMAL(10,6) NULL,           -- 同上（保留扩展）
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    settled_at    DATETIME NULL,
    INDEX idx_signal_date (signal_date),
    INDEX idx_status (status)
);
```

### 表 2：`pt_positions` — 每只股票的持仓明细

```sql
CREATE TABLE pt_positions (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    round_id      VARCHAR(32) NOT NULL,
    stock_code    VARCHAR(16) NOT NULL,
    pred_score    DECIMAL(10,6) NOT NULL,       -- 模型预测分值
    pred_rank     INT NOT NULL,                 -- 截面内预测排名（1=最高）
    -- 价格记录
    buy_price     DECIMAL(12,4) NULL,           -- 实际买入价（T+1 收盘价）
    sell_price    DECIMAL(12,4) NULL,           -- 实际卖出价（T+N 收盘价）
    -- 收益
    gross_ret     DECIMAL(10,6) NULL,           -- 毛收益（%）
    net_ret       DECIMAL(10,6) NULL,           -- 净收益（扣费后，%）
    actual_rank   INT NULL,                     -- 实际收益在截面内的排名（用于 IC）
    status        ENUM('pending','active','settled') DEFAULT 'pending',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    settled_at    DATETIME NULL,
    FOREIGN KEY (round_id) REFERENCES pt_rounds(round_id),
    INDEX idx_round_id (round_id),
    INDEX idx_stock_code (stock_code)
);
```

### 表 3：`pt_daily_prices` — 价格快照（复用已有行情表或新建）

```sql
-- 如果已有 trade_stock_daily 表，直接查该表即可
-- 若需单独缓存，建此表
CREATE TABLE pt_daily_prices (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_code VARCHAR(16) NOT NULL,
    open_price DECIMAL(12,4) NOT NULL,
    close_price DECIMAL(12,4) NOT NULL,
    UNIQUE KEY uk_date_code (trade_date, stock_code),
    INDEX idx_trade_date (trade_date)
);
```

### 表 4：`pt_benchmark` — 基准指数日收益

```sql
CREATE TABLE pt_benchmark (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    trade_date   DATE NOT NULL,
    index_name   VARCHAR(32) NOT NULL,
    close_price  DECIMAL(12,4) NOT NULL,
    daily_ret    DECIMAL(10,6) NULL,
    UNIQUE KEY uk_date_idx (trade_date, index_name)
);
```

---

## 三、核心模块实现

### 模块 1：`config.py`

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class PaperTradingConfig:
    # 持仓参数
    hold_days: int = 5              # 持仓交易日数
    top_n: int = 10                 # 每轮选股数量
    cost_rate: float = 0.002        # 双边交易成本（0.2%）

    # 可用指数池
    index_pool: dict = field(default_factory=lambda: {
        '上证50':   '000016.SH',
        '沪深300':  '000300.SH',
        '中证500':  '000905.SH',
        '中证1000': '000852.SH',
        '中证2000': '932000.CSI',
    })

    # 信号生成（对接 XGBoost 策略的参数）
    xgboost_config_path: str = 'strategist.xgboost_strategy.config'

    # 报告输出
    output_dir: str = 'strategist/paper_trading/output'
    report_min_rounds: int = 4      # 至少几轮才生成评估报告
```

---

### 模块 2：`signal_generator.py` — 信号生成

**职责**：在指定信号日，调用 XGBoost 策略，返回股票列表 + 预测分值。

```python
import pandas as pd
from datetime import date
from strategist.xgboost_strategy.data_loader import DataLoader
from strategist.xgboost_strategy.model_trainer import ModelTrainer
from strategist.xgboost_strategy.config import StrategyConfig

class SignalGenerator:
    def __init__(self, pt_config: PaperTradingConfig):
        self.pt_config = pt_config
        self.xgb_config = StrategyConfig()

    def generate(self, signal_date: date, index_name: str) -> pd.DataFrame:
        """
        在 signal_date 当天生成选股信号。
        
        关键约束：
        - 只使用 signal_date 及之前的数据
        - 训练集截止到 signal_date - 1
        - 不使用 signal_date 之后任何价格
        
        返回：
            DataFrame，列：stock_code, pred_score, pred_rank
        """
        # 1. 加载数据（截止到 signal_date）
        loader = DataLoader(self.xgb_config)
        panel, feature_cols = loader.load_and_compute_factors(
            end_date=signal_date.strftime('%Y-%m-%d'),
            index_name=index_name
        )

        # 2. 验证数据边界（防止泄露）
        max_date = pd.to_datetime(panel['trade_date']).max().date()
        assert max_date <= signal_date, \
            f"数据泄露警告：panel 包含 {max_date}，超过信号日 {signal_date}"

        # 3. 滚动训练，取 signal_date 截面的预测
        trainer = ModelTrainer(self.xgb_config)
        predictions = trainer.predict_on_date(
            panel=panel,
            feature_cols=feature_cols,
            pred_date=signal_date.strftime('%Y-%m-%d')
        )
        # predictions: DataFrame，列 stock_code, pred_score

        # 4. 排名，取 Top N
        predictions['pred_rank'] = predictions['pred_score'].rank(
            ascending=False, method='first'
        ).astype(int)
        top_n = predictions.nsmallest(self.pt_config.top_n, 'pred_rank')

        return top_n[['stock_code', 'pred_score', 'pred_rank']].reset_index(drop=True)
```

---

### 模块 3：`position_manager.py` — 持仓管理

**职责**：将信号写库，计算买卖日期，管理轮次状态。

```python
import uuid
from datetime import date, timedelta
from config.db import execute_query, execute_update

class PositionManager:
    def __init__(self, config: PaperTradingConfig):
        self.config = config

    def get_next_trading_date(self, base_date: date, offset: int = 1) -> date:
        """
        获取 base_date 之后第 offset 个交易日。
        从 trade_stock_daily 表查询实际交易日历。
        """
        sql = """
            SELECT DISTINCT trade_date 
            FROM trade_stock_daily
            WHERE trade_date > %s
            ORDER BY trade_date ASC
            LIMIT %s
        """
        rows = execute_query(sql, (base_date.strftime('%Y-%m-%d'), offset))
        if len(rows) < offset:
            raise ValueError(f"交易日历不足，无法获取 {base_date} 后第 {offset} 个交易日")
        return rows[-1]['trade_date']  # 返回最后一个，即第 offset 个

    def create_round(self, signal_date: date, index_name: str,
                     signals: pd.DataFrame) -> str:
        """
        创建新一轮记录，写入 pt_rounds 和 pt_positions。
        
        返回：round_id
        """
        round_id = f"{signal_date.strftime('%Y%m%d')}_{index_name}"
        
        # 计算买卖日期
        buy_date  = self.get_next_trading_date(signal_date, offset=1)
        sell_date = self.get_next_trading_date(buy_date,   offset=self.config.hold_days)

        # 写 pt_rounds
        execute_update("""
            INSERT INTO pt_rounds
                (round_id, signal_date, buy_date, sell_date,
                 index_name, hold_days, top_n, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            ON DUPLICATE KEY UPDATE status=status
        """, (round_id, signal_date, buy_date, sell_date,
              index_name, self.config.hold_days, self.config.top_n))

        # 写 pt_positions
        for _, row in signals.iterrows():
            execute_update("""
                INSERT INTO pt_positions
                    (round_id, stock_code, pred_score, pred_rank, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (round_id, row['stock_code'],
                  float(row['pred_score']), int(row['pred_rank'])))

        return round_id

    def get_rounds_to_settle(self) -> list:
        """
        查询所有 sell_date <= today 且 status='active' 的轮次。
        """
        sql = """
            SELECT * FROM pt_rounds
            WHERE sell_date <= CURDATE()
            AND status = 'active'
            ORDER BY sell_date ASC
        """
        return execute_query(sql)

    def get_pending_buy_rounds(self) -> list:
        """
        查询所有 buy_date <= today 且 status='pending' 的轮次（需要记录买入价）。
        """
        sql = """
            SELECT * FROM pt_rounds
            WHERE buy_date <= CURDATE()
            AND status = 'pending'
            ORDER BY buy_date ASC
        """
        return execute_query(sql)
```

---

### 模块 4：`settlement.py` — 收益结算

**职责**：在到期后从行情表读取价格，计算各项收益指标。

```python
from scipy.stats import spearmanr
import numpy as np

class SettlementEngine:
    def __init__(self, config: PaperTradingConfig):
        self.config = config

    def fill_buy_prices(self, round_id: str, buy_date: date):
        """
        T+1 日收盘后，将买入价写入 pt_positions。
        买入价 = buy_date 的收盘价（close_price）。
        更严格可改用开盘价（open_price）。
        """
        positions = execute_query(
            "SELECT * FROM pt_positions WHERE round_id=%s AND status='pending'",
            (round_id,)
        )
        for pos in positions:
            price_row = execute_query("""
                SELECT close_price FROM trade_stock_daily
                WHERE trade_date=%s AND stock_code=%s
            """, (buy_date, pos['stock_code']))

            if price_row:
                buy_price = float(price_row[0]['close_price'])
                execute_update("""
                    UPDATE pt_positions
                    SET buy_price=%s, status='active'
                    WHERE id=%s
                """, (buy_price, pos['id']))

        execute_update(
            "UPDATE pt_rounds SET status='active' WHERE round_id=%s",
            (round_id,)
        )

    def settle_round(self, round_id: str, sell_date: date,
                     benchmark_ret: float = None):
        """
        卖出日结算：读取卖出价，计算收益，写回 pt_rounds。
        
        Args:
            round_id:      轮次ID
            sell_date:     卖出日期
            benchmark_ret: 基准收益（%），从行情数据自动计算或手动传入
        """
        positions = execute_query(
            "SELECT * FROM pt_positions WHERE round_id=%s AND status='active'",
            (round_id,)
        )

        stock_rets = []
        for pos in positions:
            price_row = execute_query("""
                SELECT close_price FROM trade_stock_daily
                WHERE trade_date=%s AND stock_code=%s
            """, (sell_date, pos['stock_code']))

            if not price_row or not pos['buy_price']:
                continue  # 停牌或数据缺失，跳过

            sell_price = float(price_row[0]['close_price'])
            buy_price  = float(pos['buy_price'])

            gross_ret  = (sell_price - buy_price) / buy_price * 100
            net_ret    = gross_ret - self.config.cost_rate * 100  # 扣交易成本

            execute_update("""
                UPDATE pt_positions
                SET sell_price=%s, gross_ret=%s, net_ret=%s,
                    status='settled', settled_at=NOW()
                WHERE id=%s
            """, (sell_price, gross_ret, net_ret, pos['id']))

            stock_rets.append({
                'stock_code': pos['stock_code'],
                'pred_score': float(pos['pred_score']),
                'net_ret': net_ret
            })

        if not stock_rets:
            return

        # 计算组合收益（等权）
        portfolio_ret = np.mean([s['net_ret'] for s in stock_rets])

        # 计算 IC（Spearman）
        scores  = [s['pred_score'] for s in stock_rets]
        actuals = [s['net_ret'] for s in stock_rets]
        ic, _   = spearmanr(scores, actuals) if len(scores) >= 3 else (None, None)

        # 更新实际排名到 pt_positions（用于 RankIC）
        sorted_by_ret = sorted(stock_rets, key=lambda x: -x['net_ret'])
        for rank_i, s in enumerate(sorted_by_ret, 1):
            execute_update("""
                UPDATE pt_positions SET actual_rank=%s
                WHERE round_id=%s AND stock_code=%s
            """, (rank_i, round_id, s['stock_code']))

        # 自动计算基准收益（若未传入）
        if benchmark_ret is None:
            benchmark_ret = self._calc_benchmark_ret(round_id, sell_date)

        excess_ret = portfolio_ret - benchmark_ret if benchmark_ret is not None else None

        # 写回 pt_rounds
        execute_update("""
            UPDATE pt_rounds
            SET portfolio_ret=%s, benchmark_ret=%s, excess_ret=%s,
                ic=%s, status='settled', settled_at=NOW()
            WHERE round_id=%s
        """, (portfolio_ret, benchmark_ret, excess_ret, ic, round_id))

        return {
            'round_id': round_id,
            'portfolio_ret': portfolio_ret,
            'benchmark_ret': benchmark_ret,
            'excess_ret': excess_ret,
            'ic': ic,
            'n_stocks': len(stock_rets)
        }

    def _calc_benchmark_ret(self, round_id: str, sell_date: date) -> float:
        """从基准表自动计算区间收益"""
        round_info = execute_query(
            "SELECT * FROM pt_rounds WHERE round_id=%s", (round_id,)
        )[0]
        index_code = PaperTradingConfig().index_pool.get(round_info['index_name'])
        if not index_code:
            return None

        # 查买入和卖出日的指数价格
        prices = execute_query("""
            SELECT trade_date, close_price FROM pt_benchmark
            WHERE index_name=%s AND trade_date IN (%s, %s)
            ORDER BY trade_date
        """, (round_info['index_name'],
              round_info['buy_date'], sell_date))

        if len(prices) < 2:
            return None
        buy_p  = float(prices[0]['close_price'])
        sell_p = float(prices[1]['close_price'])
        return (sell_p - buy_p) / buy_p * 100
```

---

### 模块 5：`evaluator.py` — 绩效评估

**职责**：汇总多轮数据，计算 IC、ICIR、超额收益、夏普等指标。

```python
import numpy as np
import pandas as pd

class Evaluator:
    def __init__(self):
        pass

    def load_settled_rounds(self, index_name: str = None,
                            min_rounds: int = 4) -> pd.DataFrame:
        """加载已结算的轮次数据"""
        sql = """
            SELECT * FROM pt_rounds
            WHERE status='settled'
            {index_filter}
            ORDER BY signal_date ASC
        """.format(index_filter=f"AND index_name='{index_name}'" if index_name else "")
        rows = execute_query(sql)
        df = pd.DataFrame(rows)
        if len(df) < min_rounds:
            return None
        return df

    def compute_metrics(self, df: pd.DataFrame) -> dict:
        """
        计算全套绩效指标。
        
        输入：已结算轮次 DataFrame
        输出：指标字典
        """
        ics   = df['ic'].dropna().astype(float)
        rets  = df['portfolio_ret'].dropna().astype(float)
        excs  = df['excess_ret'].dropna().astype(float)

        # IC 系列
        ic_mean    = ics.mean()
        ic_std     = ics.std()
        icir       = ic_mean / ic_std if ic_std > 0 else np.nan
        ic_pos_pct = (ics > 0).mean() * 100

        # 收益系列
        # 复利累计：每轮相对于等权 1 份的增长
        cum_ret = (1 + rets / 100).prod() - 1  # 累计复利
        cum_exc = excs.sum()                    # 超额累计（简单加总）

        # 最大单轮亏损
        max_drawdown = rets.min()

        # 年化（假设每周一轮，52轮/年）
        n = len(rets)
        annualized_ret = ((1 + cum_ret) ** (52 / n) - 1) * 100 if n > 0 else np.nan

        # 夏普（年化超额 / 超额标准差）
        if len(excs) > 1 and excs.std() > 0:
            sharpe = (excs.mean() / excs.std()) * np.sqrt(52)
        else:
            sharpe = np.nan

        # 胜率（策略收益 > 0）
        win_rate = (rets > 0).mean() * 100

        return {
            'n_rounds':        n,
            'ic_mean':         round(ic_mean, 4),
            'ic_std':          round(ic_std, 4),
            'icir':            round(icir, 3),
            'ic_pos_pct':      round(ic_pos_pct, 1),
            'cum_ret_pct':     round(cum_ret * 100, 2),
            'cum_excess_pct':  round(cum_exc, 2),
            'annualized_ret':  round(annualized_ret, 2),
            'sharpe':          round(sharpe, 2),
            'win_rate_pct':    round(win_rate, 1),
            'max_drawdown_pct':round(max_drawdown, 2),
        }

    def interpret(self, metrics: dict) -> str:
        """
        自动生成策略结论文字。
        """
        lines = []
        ic = metrics['ic_mean']
        if ic > 0.05:
            lines.append(f"✅ IC={ic:.3f}，预测精度良好（>0.05）")
        elif ic > 0.03:
            lines.append(f"🟡 IC={ic:.3f}，有基础预测能力（0.03~0.05）")
        elif ic > 0:
            lines.append(f"🔴 IC={ic:.3f}，预测能力较弱，建议优化因子")
        else:
            lines.append(f"❌ IC={ic:.3f}<0，预测方向有问题，排查数据泄露")

        icir = metrics['icir']
        lines.append(f"{'✅' if icir>0.3 else '🔴'} ICIR={icir:.2f}，"
                     f"{'信号稳定性可接受' if icir>0.3 else '信号波动过大'}")

        ic_pos = metrics['ic_pos_pct']
        lines.append(f"{'✅' if ic_pos>55 else '🔴'} IC>0 占比 {ic_pos:.0f}%，"
                     f"{'方向正确率达标' if ic_pos>55 else '方向准确率不足'}")

        exc = metrics['cum_excess_pct']
        lines.append(f"{'✅' if exc>0 else '❌'} 累计超额收益 {exc:+.2f}%")

        lines.append(f"夏普比率 {metrics['sharpe']:.2f}，"
                     f"最大单轮亏损 {metrics['max_drawdown_pct']:.2f}%，"
                     f"胜率 {metrics['win_rate_pct']:.0f}%")
        return "\n".join(lines)
```

---

### 模块 6：`scheduler.py` — 定时任务入口

**职责**：每个交易日自动执行对应操作，核心逻辑如下：

```python
from datetime import date
import logging

logger = logging.getLogger(__name__)

class PaperTradingScheduler:
    """
    每个交易日运行一次。
    根据当天是否有需要处理的轮次，自动执行对应动作。
    
    时间轴：
        周五（信号日）→ 生成信号，创建轮次（status: pending）
        下周一（买入日）→ 记录买入价（status: active）
        下周五（卖出日）→ 结算收益（status: settled）
                        → 同时生成新一轮信号
    """
    def __init__(self):
        self.config  = PaperTradingConfig()
        self.pm      = PositionManager(self.config)
        self.se      = SettlementEngine(self.config)
        self.sg      = SignalGenerator(self.config)
        self.ev      = Evaluator()

    def run(self, today: date = None, index_name: str = '沪深300',
            is_signal_day: bool = False):
        today = today or date.today()
        logger.info(f"[PaperTrading] 开始运行，日期 {today}")

        # Step 1：记录买入价（pending → active）
        pending = self.pm.get_pending_buy_rounds()
        for r in pending:
            if r['buy_date'] <= today:
                logger.info(f"[填入买入价] {r['round_id']}")
                self.se.fill_buy_prices(r['round_id'], r['buy_date'])

        # Step 2：结算到期轮次（active → settled）
        to_settle = self.pm.get_rounds_to_settle()
        for r in to_settle:
            logger.info(f"[结算] {r['round_id']}")
            result = self.se.settle_round(r['round_id'], r['sell_date'])
            if result:
                logger.info(f"  → 策略收益 {result['portfolio_ret']:.2f}%，"
                            f"超额 {result['excess_ret']:.2f}%，IC={result['ic']:.3f}")

        # Step 3：生成新信号（仅在信号日执行）
        if is_signal_day:
            logger.info(f"[生成信号] {today} {index_name}")
            signals = self.sg.generate(today, index_name)
            round_id = self.pm.create_round(today, index_name, signals)
            logger.info(f"  → 创建轮次 {round_id}，选出 {len(signals)} 只股票")
            logger.info(f"  → 买入日: {self.pm.get_next_trading_date(today, 1)}")

        # Step 4：打印当前评估（每次运行都输出）
        df = self.ev.load_settled_rounds(index_name)
        if df is not None:
            metrics = self.ev.compute_metrics(df)
            print(f"\n{'='*50}")
            print(f"[{index_name}] 已结算 {metrics['n_rounds']} 轮")
            print(self.ev.interpret(metrics))
            print('='*50)
```

---

### 模块 7：`run_paper_trading.py` — 手动运行入口

```python
"""
手动运行入口。
用法：
  # 生成今日信号（周五收盘后运行）
  python -m strategist.paper_trading.run_paper_trading --action signal --index 沪深300

  # 结算并填入买入价（每日盘后运行）
  python -m strategist.paper_trading.run_paper_trading --action settle

  # 查看评估报告
  python -m strategist.paper_trading.run_paper_trading --action report --index 沪深300

  # 全自动（结算 + 如果今天是周五则生成信号）
  python -m strategist.paper_trading.run_paper_trading --action auto
"""
import argparse
from datetime import date

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', choices=['signal','settle','report','auto'],
                        required=True)
    parser.add_argument('--index', default='沪深300')
    parser.add_argument('--date', default=None, help='指定日期 YYYY-MM-DD')
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    scheduler = PaperTradingScheduler()

    if args.action == 'signal':
        scheduler.run(today, args.index, is_signal_day=True)

    elif args.action == 'settle':
        scheduler.run(today, args.index, is_signal_day=False)

    elif args.action == 'report':
        ev = Evaluator()
        df = ev.load_settled_rounds(args.index, min_rounds=1)
        if df is None:
            print("暂无已结算数据")
        else:
            metrics = ev.compute_metrics(df)
            print(f"\n{'='*60}")
            print(f"策略评估报告 — {args.index}（{len(df)} 轮）")
            print('='*60)
            for k, v in metrics.items():
                print(f"  {k:<22} {v}")
            print('\n结论：')
            print(ev.interpret(metrics))

    elif args.action == 'auto':
        is_friday = today.weekday() == 4  # 周五
        scheduler.run(today, args.index, is_signal_day=is_friday)

if __name__ == '__main__':
    main()
```

---

## 四、标准操作 SOP

### 每周固定动作（以沪深300为例）

```
周五 17:00  盘后
  python -m strategist.paper_trading.run_paper_trading \
    --action signal --index 沪深300
  # 生成信号，写入 pt_rounds（status=pending）和 pt_positions

下周一 16:30  盘后
  python -m strategist.paper_trading.run_paper_trading \
    --action settle --index 沪深300
  # 自动读取买入价，pt_rounds 变为 active

下周五 16:30  盘后
  python -m strategist.paper_trading.run_paper_trading \
    --action auto --index 沪深300
  # 结算上轮（active → settled），同时生成新一轮信号
```

### 定时任务配置（crontab）

```bash
# 每个交易日 16:30 自动结算
30 16 * * 1-5 cd /path/to/myTrader && python -m strategist.paper_trading.run_paper_trading --action auto --index 沪深300
```

---

## 五、任务拆分与优先级

| # | 任务 | 工期 | 优先级 | 依赖 |
|---|------|------|--------|------|
| T1 | 建表（4张 SQL） | 0.5天 | 🔴 最高 | — |
| T2 | `config.py` + `position_manager.py` | 0.5天 | 🔴 最高 | T1 |
| T3 | `settlement.py`（核心结算逻辑） | 1天 | 🔴 最高 | T1, T2 |
| T4 | `signal_generator.py`（对接 XGBoost） | 1天 | 🔴 最高 | T2, XGBoost模块 |
| T5 | `evaluator.py` + 指标计算 | 0.5天 | 🟡 高 | T3 |
| T6 | `scheduler.py` + `run_paper_trading.py` | 0.5天 | 🟡 高 | T2~T5 |
| T7 | 基准行情数据入库（`pt_benchmark`） | 0.5天 | 🟡 高 | T1 |
| T8 | 端到端集成测试（用历史数据跑一遍） | 1天 | 🟡 高 | T1~T7 |
| T9 | `reporter.py`（Markdown/CSV 报告） | 0.5天 | 🟢 中 | T5 |
| T10 | crontab 配置 + 日志告警 | 0.5天 | 🟢 中 | T6 |

**推荐执行顺序**：T1 → T2 → T3 → T7 → T5 → T4 → T6 → T8 → T9 → T10

---

## 六、端到端测试方法（历史回放）

在真实信号积累前，用历史数据验证系统逻辑是否正确：

```python
# test_historical_replay.py
# 用 2024 年的历史数据，按周模拟信号 → 买入 → 结算 → 评估

from datetime import date

# 选取历史上的周五列表
test_signal_dates = [
    date(2024, 1, 5),   # 周五
    date(2024, 1, 12),
    date(2024, 1, 19),
    date(2024, 1, 26),
    date(2024, 2, 2),
    # ... 继续
]

scheduler = PaperTradingScheduler()
for sig_date in test_signal_dates:
    # 生成信号
    scheduler.run(sig_date, '沪深300', is_signal_day=True)
    
    # 模拟买入日
    buy_date = scheduler.pm.get_next_trading_date(sig_date, 1)
    scheduler.run(buy_date, '沪深300', is_signal_day=False)
    
    # 模拟卖出日
    sell_date = scheduler.pm.get_next_trading_date(buy_date, 5)
    scheduler.run(sell_date, '沪深300', is_signal_day=False)

# 最终评估
ev = Evaluator()
df = ev.load_settled_rounds('沪深300')
metrics = ev.compute_metrics(df)
print(ev.interpret(metrics))
```

**关键验证点**：
- 所有 `buy_price` 均来自 `signal_date + 1` 的收盘价，不早于此
- IC 在 [-1, 1] 之间，不异常偏高（>0.15 需警惕）
- `pt_rounds.ic` 与手动用 Excel 算的 Spearman 结果一致

---

## 七、有效性判断标准

| 指标 | 无效 | 有待验证 | 有效 |
|------|------|----------|------|
| IC 均值 | < 0 | 0 ~ 0.03 | > 0.03 |
| ICIR | < 0 | 0 ~ 0.3 | > 0.3 |
| IC>0 占比 | < 50% | 50% ~ 55% | > 55% |
| 累计超额收益 | 负 | 接近 0 | 持续为正 |
| 最小验证轮次 | — | — | ≥ 8 轮 |

---

*文档版本：1.0 | 日期：2026-03-27*
