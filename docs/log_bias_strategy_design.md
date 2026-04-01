# 乖离率策略设计文档

> 基于刘晨明乖离率指标的日频计算策略

## 1. 背景

参考广发策略首席刘晨明的研究：
- 原文：《如何区分主线是调整还是终结？》
- 核心目的：追踪主线行业，判断趋势是调整还是终结

## 2. 核心算法

### 2.1 公式（减法版）

```
log_bias = (ln(close) - EMA(ln(close), 20)) * 100
```

- 使用自然对数 `ln`
- EMA 窗口期 20 日
- 乘以 100 转换为百分比

### 2.2 Python 实现

```python
import pandas as pd
import numpy as np

def calculate_log_bias(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    计算乖离率
    
    Args:
        df: 必须包含 'close' 列，索引为日期
        window: EMA 窗口期，默认 20
        
    Returns:
        DataFrame with columns: [close, ln_close, ema_ln, log_bias]
    """
    # 1. 取自然对数
    df['ln_close'] = np.log(df['close'])
    
    # 2. 计算对数收盘价的 EMA
    # span=20 对应通达信的 EMA(X, 20)，adjust=False 保证递归逻辑一致
    df['ema_ln'] = df['ln_close'].ewm(span=window, adjust=False).mean()
    
    # 3. 减法版乖离率公式
    df['log_bias'] = (df['ln_close'] - df['ema_ln']) * 100
    
    return df[['close', 'ln_close', 'ema_ln', 'log_bias']]
```

### 2.3 通达信公式

```
EMA20:= EMA(LN(CLOSE), 20);
LOGBIAS: (LN(CLOSE) - EMA20) * 100;
过热线: 15, COLORRED, DOTLINE;
失速线: 5, COLORYELLOW, DOTLINE;
止损参考线: -5, COLORGREEN, DOTLINE;
零轴: 0, COLORGRAY, DOTLINE;
```

### 2.4 注意事项

- **数据预热期**：至少 120 个交易日，EMA 才能收敛到稳定值
- **低价标的**：减法版适用于 ETF 等低价标的，不会出现除零或正负颠倒问题

## 3. 信号状态机

### 3.1 状态定义

| 状态 | 英文 | 阈值条件 | 动作建议 |
|------|------|----------|----------|
| 过热 | `overheat` | `log_bias > 15` | 不追高，等回调 |
| 突破 | `breakout` | `log_bias` 从 <5 上穿 5 | 买入/加仓，主线启动 |
| 回抽 | `pullback` | `log_bias` 在 [0, 5) 且近 20 日曾 >5 | 低吸机会 |
| 正常 | `normal` | `log_bias` 在 [-5, 5) | 趋势中性 |
| 失速 | `stall` | `log_bias < -5` | 止损/离场 |

### 3.2 状态转换规则

```
                    ┌─────────────┐
                    │   overheat  │ (>15)
                    └──────┬──────┘
                           │ 回落
                           ▼
┌─────────┐  上穿5  ┌─────────────┐  回落到[0,5)  ┌─────────────┐
│  normal │ ──────► │  breakout   │ ────────────► │  pullback   │
│ [-5,5)  │         │   (>=5)     │               │   [0,5)     │
└────┬────┘         └─────────────┘               └──────┬──────┘
     │                                                   │
     │ <-5                                               │ <-5
     ▼                                                   ▼
┌─────────────┐                                  ┌─────────────┐
│    stall    │ ◄────────────────────────────────│    stall    │
│   (<-5)     │                                  │   (<-5)     │
└─────────────┘                                  └─────────────┘
```

### 3.3 冷却期机制

- **失速后冷却期**：10 个交易日
- 跌破 -5 后，即使反弹到 0 以上，也需等待 10 日才能重新触发突破信号
- 目的：过滤"假反弹"

### 3.4 使用心得（来自实战）

1. **不上 5% 不够强**：主线行业应能突破 5%，否则缺乏"龙头气质"
2. **回抽两步走**：触及 5% → 回调到 0 附近获支撑 → 再突破，是走强信号
3. **品种择强**：用乖离率对比同类品种，选更强的
4. **止损后不轻易入场**：跌破 -5% 后需等待重新站上 5%
5. **逆练真经**：对价值类品种（银行、红利），-5% 到 5% 可作为震荡区间高抛低吸

## 4. 数据源

### 4.1 复用现有数据库

- **表**：`trade_etf_daily`（线上 MySQL）
- **字段**：`fund_code`, `trade_date`, `close_price`
- **数据量**：1000+ 只 ETF，最新数据到 2026-03-31

### 4.2 默认追踪标的

```python
DEFAULT_ETFS = {
    # 科技成长
    '159995.SZ': '芯片ETF',
    '515050.SH': '5GETF',
    '516160.SH': '新能源车ETF',
    '515790.SH': '光伏ETF',
    '159941.SZ': '纳指ETF',
    # 消费医药
    '512690.SH': '酒ETF',
    '512010.SH': '医药ETF',
    # 周期金融
    '512880.SH': '证券ETF',
    '515220.SH': '煤炭ETF',
    '518880.SH': '黄金ETF',
    # 宽基
    '510300.SH': '沪深300ETF',
    '588000.SH': '科创50ETF',
}
```

## 5. 存储设计

### 5.1 数据库表

```sql
CREATE TABLE IF NOT EXISTS trade_log_bias_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL COMMENT '标的代码',
    trade_date DATE NOT NULL COMMENT '交易日',
    close_price DOUBLE COMMENT '收盘价',
    ln_close DOUBLE COMMENT 'ln(close)',
    ema_ln_20 DOUBLE COMMENT 'EMA(ln_close, 20)',
    log_bias DOUBLE COMMENT '乖离率 (ln_close - ema_ln) * 100',
    signal_state VARCHAR(20) COMMENT '信号状态: overheat/breakout/pullback/normal/stall',
    prev_state VARCHAR(20) COMMENT '前一日状态',
    last_breakout_date DATE COMMENT '最近突破日期',
    last_stall_date DATE COMMENT '最近失速日期',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date (ts_code, trade_date),
    INDEX idx_date (trade_date),
    INDEX idx_signal (signal_state, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='乖离率日频数据';
```

## 6. 模块结构

```
strategist/log_bias/
├── config.py              # 配置：窗口期、阈值、冷却期、默认 ETF 列表
├── calculator.py          # 核心算法：calculate_log_bias()
├── signal_detector.py     # 信号状态机（含冷却期逻辑）
├── data_loader.py         # 数据加载（复用 trade_etf_daily）
├── storage.py             # 结果存储到 trade_log_bias_daily
├── report_generator.py    # Markdown 报告生成
├── run_daily.py           # 日频执行入口
└── tests/
    ├── test_calculator.py     # 单测：算法正确性
    ├── test_signal_detector.py # 单测：信号触发逻辑
    └── test_integration.py    # 集成测试
```

## 7. 任务列表

| # | 任务 | 文件 | 描述 |
|---|------|------|------|
| 1 | 配置文件 | `config.py` | 阈值、窗口期、冷却期、默认 ETF 列表、输出路径 |
| 2 | 核心算法 | `calculator.py` | `calculate_log_bias(df, window=20)` |
| 3 | 信号状态机 | `signal_detector.py` | 状态判定 + 冷却期逻辑 |
| 4 | 数据加载 | `data_loader.py` | 从 `trade_etf_daily` 加载，支持增量 |
| 5 | 存储层 | `storage.py` | 建表 + UPSERT |
| 6 | 报告生成 | `report_generator.py` | Markdown 报告 |
| 7 | 执行入口 | `run_daily.py` | CLI 入口，支持 `--date` 参数 |
| 8 | 单测-算法 | `tests/test_calculator.py` | 见下方测试用例 |
| 9 | 单测-信号 | `tests/test_signal_detector.py` | 见下方测试用例 |
| 10 | 集成测试 | `tests/test_integration.py` | 端到端流程 |

## 8. 测试用例设计

### 8.1 test_calculator.py

```python
import pytest
import pandas as pd
import numpy as np

class TestLogBiasCalculator:
    
    def test_log_bias_basic(self):
        """基础计算正确性（手工验算对比）"""
        # 构造简单数据
        df = pd.DataFrame({
            'close': [10.0, 10.5, 11.0, 10.8, 11.2]
        })
        result = calculate_log_bias(df)
        
        # 验证 ln_close
        assert np.isclose(result['ln_close'].iloc[0], np.log(10.0))
        
        # 验证 log_bias 符号：收盘价上涨时 log_bias > 0
        assert result['log_bias'].iloc[-1] > 0
    
    def test_log_bias_ema_convergence(self):
        """EMA 收敛性（120 日后稳定）"""
        # 构造 200 日恒定价格数据
        df = pd.DataFrame({
            'close': [100.0] * 200
        })
        result = calculate_log_bias(df)
        
        # 120 日后 log_bias 应接近 0
        assert abs(result['log_bias'].iloc[120]) < 0.01
        assert abs(result['log_bias'].iloc[-1]) < 0.001
    
    def test_log_bias_nan_handling(self):
        """空值/缺失数据处理"""
        df = pd.DataFrame({
            'close': [10.0, np.nan, 11.0, 10.5]
        })
        result = calculate_log_bias(df)
        
        # NaN 应该传播
        assert pd.isna(result['ln_close'].iloc[1])
    
    def test_log_bias_low_price(self):
        """低价标的（<1 元）不报错"""
        df = pd.DataFrame({
            'close': [0.5, 0.52, 0.48, 0.51, 0.50]
        })
        result = calculate_log_bias(df)
        
        # 不应报错，且有有效值
        assert not result['log_bias'].isna().all()
```

### 8.2 test_signal_detector.py

```python
import pytest
from datetime import date, timedelta

class TestSignalDetector:
    
    def test_breakout_signal(self):
        """log_bias 从 4 -> 6 触发突破"""
        detector = SignalDetector()
        
        # 模拟数据：前一日 log_bias=4，今日 log_bias=6
        prev_state = {'log_bias': 4.0, 'signal_state': 'normal'}
        curr_state = {'log_bias': 6.0}
        
        result = detector.detect(curr_state, prev_state)
        assert result['signal_state'] == 'breakout'
    
    def test_pullback_signal(self):
        """突破后回落到 [0,5) 触发回抽"""
        detector = SignalDetector()
        
        # 模拟：之前突破过，现在回落到 3
        prev_state = {
            'log_bias': 7.0, 
            'signal_state': 'breakout',
            'last_breakout_date': date.today() - timedelta(days=5)
        }
        curr_state = {'log_bias': 3.0}
        
        result = detector.detect(curr_state, prev_state)
        assert result['signal_state'] == 'pullback'
    
    def test_stall_signal(self):
        """log_bias < -5 触发失速"""
        detector = SignalDetector()
        
        prev_state = {'log_bias': -3.0, 'signal_state': 'normal'}
        curr_state = {'log_bias': -6.0}
        
        result = detector.detect(curr_state, prev_state)
        assert result['signal_state'] == 'stall'
    
    def test_overheat_signal(self):
        """log_bias > 15 触发过热"""
        detector = SignalDetector()
        
        prev_state = {'log_bias': 12.0, 'signal_state': 'breakout'}
        curr_state = {'log_bias': 16.0}
        
        result = detector.detect(curr_state, prev_state)
        assert result['signal_state'] == 'overheat'
    
    def test_cooldown_period(self):
        """失速后 10 日内不触发突破"""
        detector = SignalDetector(cooldown_days=10)
        
        # 5 天前失速
        prev_state = {
            'log_bias': 4.0,
            'signal_state': 'normal',
            'last_stall_date': date.today() - timedelta(days=5)
        }
        curr_state = {'log_bias': 6.0}
        
        result = detector.detect(curr_state, prev_state)
        # 仍在冷却期，不应触发突破
        assert result['signal_state'] != 'breakout'
        assert result['signal_state'] == 'normal'
    
    def test_cooldown_expired(self):
        """冷却期结束后可触发突破"""
        detector = SignalDetector(cooldown_days=10)
        
        # 15 天前失速，冷却期已过
        prev_state = {
            'log_bias': 4.0,
            'signal_state': 'normal',
            'last_stall_date': date.today() - timedelta(days=15)
        }
        curr_state = {'log_bias': 6.0}
        
        result = detector.detect(curr_state, prev_state)
        assert result['signal_state'] == 'breakout'
```

### 8.3 test_integration.py

```python
import pytest
from datetime import date

class TestIntegration:
    
    def test_full_pipeline(self):
        """选 1 只 ETF，跑完整流程"""
        # 1. 加载数据
        loader = DataLoader(env='online')
        df = loader.load('510300.SH', lookback_days=300)
        assert len(df) > 120  # 确保有足够数据
        
        # 2. 计算乖离率
        result = calculate_log_bias(df)
        assert 'log_bias' in result.columns
        
        # 3. 检测信号
        detector = SignalDetector()
        signals = detector.detect_all(result)
        assert 'signal_state' in signals.columns
        
        # 4. 存储
        storage = Storage(env='online')
        count = storage.save('510300.SH', signals)
        assert count > 0
    
    def test_incremental_update(self):
        """增量更新逻辑"""
        loader = DataLoader(env='online')
        storage = Storage(env='online')
        
        # 获取数据库中最新日期
        latest = storage.get_latest_date('510300.SH')
        
        # 只加载新数据
        df = loader.load('510300.SH', start_date=latest)
        
        # 应该只有少量新数据
        assert len(df) <= 5
    
    def test_report_generation(self):
        """报告文件生成"""
        generator = ReportGenerator(
            output_dir='/Users/zhaobo/Documents/notes/Finance/Output'
        )
        
        # 生成报告
        report_path = generator.generate(date.today())
        
        # 验证文件存在
        assert os.path.exists(report_path)
        
        # 验证内容
        with open(report_path, 'r') as f:
            content = f.read()
            assert '乖离率' in content
            assert 'log_bias' in content
```

## 9. 报告输出

### 9.1 输出路径

```
/Users/zhaobo/Documents/notes/Finance/Output/LogBias_YYYYMMDD.md
```

### 9.2 报告模板

```markdown
# 乖离率日报 - 2026-04-01

## 信号汇总

| 状态 | 数量 | 标的 |
|------|------|------|
| [RED] 过热 | 1 | 芯片ETF |
| [YELLOW] 突破 | 2 | 5GETF, 新能源车ETF |
| [GREEN] 回抽 | 1 | 光伏ETF |
| [GRAY] 失速 | 0 | - |

## 详细数据

| 标的 | 代码 | 收盘价 | 乖离率 | 状态 | 变化 |
|------|------|--------|--------|------|------|
| 芯片ETF | 159995.SZ | 1.234 | 16.5% | [RED] 过热 | 突破->过热 |
| 5GETF | 515050.SH | 2.345 | 6.2% | [YELLOW] 突破 | 正常->突破 |
| ... | ... | ... | ... | ... | ... |

## 趋势图

(可选：ASCII 图或链接到图片)

---
生成时间: 2026-04-01 16:30:00
```

## 10. 执行方式

```bash
# 手动执行（计算今日数据）
python -m strategist.log_bias.run_daily

# 指定日期
python -m strategist.log_bias.run_daily --date 2026-03-31

# 回填历史数据
python -m strategist.log_bias.run_daily --start 2025-01-01 --end 2026-03-31
```

## 11. 参考资料

1. 刘晨明《如何区分主线是调整还是终结？》
2. 刘晨明《6大指标看居民入市：温度几何？》
3. 《刘晨明乖离率怎么用，我的一点心得》

---

*文档创建: 2026-04-01*
