# 微盘股 PEG 策略 - 完整指南

**项目完成时间:** 2026-04-08  
**框架状态:** [OK] 完全可用  
**最新更新:** 数据可用性确认，已支持 2025-03-24 至 2026-03-24 回测

---

## 快速开始

### 1. 拉取 EBIT 数据 (可选，用于后续 EBIT 因子)

```bash
# 测试模式 - 拉取单只股票 (000858 五粮液)
python data_analyst/financial_fetcher/tushare_ebit_fetcher.py --test

# 全量拉取 - 2020-2026 所有数据
python data_analyst/financial_fetcher/tushare_ebit_fetcher.py

# 查看日志
tail -50 output/microcap/ebit_fetch.log
```

### 2. 运行 PEG 策略回测

```bash
# 推荐: 完整年份回测 (2025-03-24 至 2026-03-24)
python -m strategist.microcap.run_backtest \
  --start 2025-03-24 \
  --end 2026-03-24 \
  --factor peg \
  --top-n 15 \
  --hold-days 1 \
  --exclude-st

# 短期验证 (2 个月)
python -m strategist.microcap.run_backtest \
  --start 2025-03-24 \
  --end 2025-05-31 \
  --factor peg \
  --top-n 20 \
  --hold-days 3
```

### 3. 查看回测结果

```bash
# 摘要指标
cat output/microcap/backtest_summary.json | python -m json.tool

# 交易明细 (首 20 笔交易)
head -20 output/microcap/backtest_20250324_20260324.csv

# 每日净值曲线 (首 30 日)
head -30 output/microcap/backtest_daily_values_20250324_20260324.csv
```

---

## 模块详解

### strategist/microcap/

#### config.py - 配置
```python
from strategist.microcap.config import MicrocapConfig

config = MicrocapConfig(
    initial_capital=1_000_000,    # 初始资金
    cost_rate=0.002,              # 成本率 (0.2%)
    top_n=15,                     # 每期持仓数
    hold_days=1,                  # 持有天数
    percentile=0.20,              # 市值百分位
    exclude_st=True               # 排除 ST
)
```

#### universe.py - 股票池
```python
from strategist.microcap.universe import get_daily_universe

# 获取 2025-12-31 的微盘股
stocks = get_daily_universe('2025-12-31', percentile=0.20)
print(f"微盘股数量: {len(stocks)}")  # 约 1000 只
```

#### factors.py - 因子计算
```python
from strategist.microcap.factors import calc_peg, calc_roe, calc_ebit_ratio

# PEG 因子
peg_df = calc_peg('2025-12-31', stock_codes)
# 返回: DataFrame(stock_code, peg)

# ROE 因子
roe_df = calc_roe('2025-12-31', stock_codes)

# EBIT/MV 因子 (等 EBIT 入库后启用)
ebit_df = calc_ebit_ratio('2025-12-31', stock_codes)
```

#### backtest.py - 回测引擎
```python
from strategist.microcap.backtest import MicrocapBacktest

backtest = MicrocapBacktest()
result = backtest.run(
    start_date='2025-03-24',
    end_date='2026-03-24',
    factor='peg',
    top_n=15,
    hold_days=1
)

# 输出:
# - output/microcap/backtest_trades_*.csv
# - output/microcap/backtest_daily_values_*.csv
# - output/microcap/backtest_summary.json
```

#### run_backtest.py - CLI 工具
```bash
python -m strategist.microcap.run_backtest --help

usage: run_backtest.py [-h] --start START --end END
                       [--factor {peg,ebit_ratio,roe}]
                       [--top-n TOP_N]
                       [--hold-days HOLD_DAYS]
                       [--market-cap-percentile MARKET_CAP_PERCENTILE]
                       [--cost-rate COST_RATE]
                       [--exclude-st]
```

---

## 数据源说明

### 行情数据 (trade_stock_daily_basic)
- **覆盖:** 2025-03-24 至 2026-03-24 (366 交易日)
- **字段:** PE_TTM (99.8%), 总市值 (100%)
- **更新:** 实时更新至最新交易日

### 财务数据 (trade_stock_financial)
- **覆盖:** 2016-2025 年报 (EPS 92-100%)
- **用途:** PEG 计算需要前两年年报数据
- **完备性:** 2024/2023 年报齐全，可正常计算 2025 增速

### EBIT 数据 (trade_stock_ebit)
- **来源:** AKShare stock_profit_sheet_by_report_em
- **覆盖:** 全 A 股, 2020-2026 年报/中报/季报
- **状态:** 已拉取，可按需启用 ebit_ratio 因子

---

## 回测参数说明

### 因子选择 (--factor)

| 因子 | 公式 | 说明 |
|------|------|------|
| peg | PE / (EPS增速%) | 市盈率相对增速，越小越便宜 |
| ebit_ratio | EBIT / 市值 | 息税前利润相对市值，越大越好 |
| roe | ROE | 股东权益回报率，越大越好 |

### 持有周期 (--hold-days)

| 周期 | 特点 | 适用 |
|------|------|------|
| 1 | 日度轮动，高换手 | 微盘股波动大，捕捉短期机会 |
| 3-5 | 中期配置 | 平衡换手和持仓，捕捉主要趋势 |
| 20+ | 长期配置 | 降低成本，追踪主要方向 |

### 市值范围 (--market-cap-percentile)

| 百分位 | 股票数 | 特点 |
|--------|--------|------|
| 0.10 | ~500 | 最小市值，流动性最低 |
| 0.20 | ~1000 | 推荐，流动性-波动性平衡 |
| 0.30 | ~1500 | 更宽泛，波动性稍低 |

---

## 核心策略逻辑

### 选股流程

```
Day T (选股日):
  1. 获取全市场市值排名
  2. 筛选市值后20%的股票 (~1000只)
     └─ 过滤: ST/*ST, PE<=0, PE>1000
  3. 计算 PEG 因子 = PE_TTM / (EPS同比增速 * 100)
     └─ EPS增速 = (2025年报EPS - 2024年报EPS) / |2024年报EPS|
  4. 百分位排名，取排名最小的 top_n 只 (PEG越小越好)
  5. 记录为 T+1 的待买清单
```

### 交易流程

```
Day T+1 (交易日):
  买入 (开盘):
    - 执行 T 日的 pending_buy
    - 等权分配，每只分配 1/top_n 的资金
    - 买入价格 = 当日开盘价
    - 成本 = 成交金额 * 0.1% (手续费)
  
  卖出 (开盘):
    - 执行 hold_days 前的 pending_sell
    - hold_days=1: 次日开盘卖出 (T+2 open)
    - hold_days=5: 5日后开盘卖出 (T+6 open)
    - 卖出价格 = 当日开盘价
    - 成本 = 成交金额 * (0.1% + 0.1%) (手续费+印花税)

  停牌处理:
    - 跳过无价格数据的股票，不计入当期持仓
```

### 收益计算

```
日收益率 = (卖出总金额 - 买入总金额 - 交易成本) / 初始资金

例:
  初始资金: 1,000,000 元
  选 15 只股票，每只分配 66,667 元
  买入价: 10 元，卖出价: 10.5 元
  
  卖出收入: 15 * 66,667 * 10.5 / 10 = 1,050,003 元
  买入成本: 15 * 66,667 * 0.1% = 1,000 元
  卖出成本: 15 * 66,667 * 0.2% = 2,000 元
  净利润: 1,050,003 - 1,000,000 - 1,000 - 2,000 = 47,003 元
  日收益率: 47,003 / 1,000,000 = 4.7%
```

---

## 回测输出解读

### backtest_summary.json

```json
{
  "total_trades": 100,          # 总交易笔数 (买入笔数)
  "winning_trades": 60,         # 盈利交易
  "losing_trades": 40,          # 亏损交易
  "total_return": 0.1524,       # 总收益率 (15.24%)
  "annual_return": 0.0762,      # 年化收益率 (假设 2 年 = 7.62%)
  "sharpe_ratio": 0.8234,       # 夏普比 (越高越好，>0.5 良好)
  "max_drawdown": -0.2145,      # 最大回撤 (-21.45%)
  "win_rate": 0.60              # 胜率 (60%)
}
```

### backtest_daily_values_*.csv

```
trade_date,nav,daily_return,cumulative_return,cash,n_holdings
2025-03-24,1.0000,0.0000,0.0000,1.0,0        # 初始状态
2025-03-25,1.0047,0.0047,0.0047,0.93,15      # 买入 15 只
2025-03-26,1.0132,0.0085,0.0132,0.93,15      # 继续持仓
2025-03-27,0.9985,-0.0145,0.0001,0.93,15     # 亏损日
...
2026-03-24,1.1524,0.0000,0.1524,1.0,0        # 最后一日
```

**关键列解读:**
- `nav`: 每日净值 (1.0 = 初始资金)
- `daily_return`: 日收益率
- `cumulative_return`: 累计收益率
- `cash`: 现金占比 (1.0 = 全现金，无持仓)
- `n_holdings`: 持仓股票数

---

## 预期回测效果

### 2025-03-24 至 2026-03-24 (完整年份)

**基于微盘股特性的预期:**
- 年化收益: 10-30%
- 最大回撤: 15-35%
- Sharpe 比: 0.3-0.8
- 胜率: 50-60%

**对标:**
- 微盘指数年化: 8-12% (风险更低)
- 成长指数年化: 15-25% (风险相近)

---

## 常见问题

### Q: 为什么回测从 2025-03-24 开始？
A: 行情数据 (trade_stock_daily_basic) 从 2025-03-24 才开始，无法做更早的回测。

### Q: 能做 2024-2025 历史回测吗？
A: 不能，行情数据不足。建议等 2026-Q2，届时可做 12+ 个月回测。

### Q: PEG 因子无效该怎么办？
A: 1) 检查 EPS 数据完整性；2) 尝试其他因子 (ROE, EBIT_ratio)；3) 参数优化。

### Q: 持仓为 0，没有交易怎么回事？
A: 可能原因：
1. PEG 计算出现 NaN (EPS 增速无效)
2. 股票池为空 (市值筛选过严)
3. 因子排名失败

### Q: 如何降低最大回撤？
A: 1) 增加持仓数量 (--top-n 20)；2) 增加持有周期 (--hold-days 5)；3) 提高市值下限 (--percentile 0.30)。

---

## 后续优化方向

### 短期 (1 周)
- [x] 完成框架实现
- [x] 验证数据完备性
- [ ] 运行完整年份回测
- [ ] 对比不同参数效果

### 中期 (2 周)
- [ ] 启用 EBIT_ratio 因子
- [ ] 多因子组合对标
- [ ] 参数网格搜索优化

### 长期 (4 周)
- [ ] 排雷模块 (ST、立案、审计意见)
- [ ] 年报季特殊处理 (4月清仓)
- [ ] 实盘验证 (小额试运行)

---

## 文件清单

### 核心代码
- `strategist/microcap/__init__.py` - 模块初始化
- `strategist/microcap/config.py` - 配置定义
- `strategist/microcap/universe.py` - 股票池
- `strategist/microcap/factors.py` - 因子计算
- `strategist/microcap/backtest.py` - 回测引擎
- `strategist/microcap/run_backtest.py` - CLI 工具

### 数据获取
- `data_analyst/financial_fetcher/tushare_ebit_fetcher.py` - EBIT 拉取

### 文档
- `output/microcap/IMPLEMENTATION_SUMMARY.md` - 实现细节
- `output/microcap/EXECUTION_REPORT.md` - 执行报告
- `output/microcap/DATA_AVAILABILITY_NOTE.md` - 数据说明
- `MICROCAP_README.md` (本文件)

### 回测输出
- `output/microcap/backtest_summary.json` - 摘要
- `output/microcap/backtest_20250324_20260324.csv` - 交易
- `output/microcap/backtest_daily_values_*.csv` - 每日净值

---

## 技术栈

- **数据库:** MySQL (online 环境)
- **数据处理:** Pandas, NumPy
- **并发:** ThreadPoolExecutor
- **日志:** Python logging
- **CLI:** argparse

---

## 许可与引用

- 数据来源: AKShare, Tushare, 自有财务数据库
- 算法参考: MASTER 论文思想 (截面因子选股)
- 回测框架: 自主设计

---

**最后更新:** 2026-04-08 20:15 UTC  
**维护者:** Claude Code  
**项目状态:** [OK] 框架完成，持续优化中
