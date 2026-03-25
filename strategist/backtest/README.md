# 通用回测框架

面向个股的通用回测引擎，支持多股票组合、完整的资金管理和风控。

## 特性

- ✅ **多股票组合管理**：支持同时持有多只股票
- ✅ **完整资金管理**：现金+持仓，实时计算可用资金
- ✅ **交易成本**：手续费、滑点、印花税
- ✅ **风控机制**：止损、止盈、持仓到期
- ✅ **仓位管理**：等权重、风险平价、凯利公式
- ✅ **完整指标**：夏普比率、索提诺比率、卡玛比率、最大回撤等
- ✅ **基准对比**：支持与基准指数对比
- ✅ **报告生成**：Markdown报告 + CSV数据导出

## 快速开始

### 1. 基本使用

```python
from strategist.backtest import BacktestEngine, BacktestConfig, ReportGenerator
import pandas as pd

# 配置回测参数
config = BacktestConfig(
    initial_cash=1_000_000,      # 初始资金100万
    max_positions=10,             # 最大持仓10只
    default_hold_days=60,         # 持仓60天
    default_stop_loss=-0.10,      # 止损-10%
    default_take_profit=0.20,     # 止盈+20%
)

# 准备信号数据（策略输出）
signals = pd.DataFrame({
    'date': ['2023-01-05', '2023-01-10'],
    'stock_code': ['000001.SZ', '600000.SH'],
    'signal_type': ['momentum', 'reversal'],
    'weight': [1.0, 0.8],  # 可选，信号权重
})

# 准备价格数据
price_data = {
    '000001.SZ': pd.DataFrame({
        'trade_date': [...],
        'open': [...],
        'close': [...],
    }),
    '600000.SH': pd.DataFrame({...}),
}

# 运行回测
engine = BacktestEngine(config)
result = engine.run(signals, price_data)

# 生成报告
ReportGenerator.generate_full_report(
    result=result,
    output_dir='output/',
    strategy_name="我的策略"
)
```

### 2. 配置说明

```python
@dataclass
class BacktestConfig:
    # 资金配置
    initial_cash: float = 1_000_000          # 初始资金
    
    # 交易成本
    commission: float = 0.0003               # 手续费率 0.03%
    slippage: float = 0.001                  # 滑点率 0.1%
    stamp_tax: float = 0.001                 # 印花税 0.1% (仅卖出)
    
    # 仓位管理
    max_positions: int = 10                  # 最大持仓数
    position_sizing: str = 'equal'           # 仓位分配方式
    single_position_limit: float = 0.1       # 单只股票最大仓位10%
    
    # 风控配置
    default_hold_days: int = 60              # 默认持仓天数
    default_stop_loss: float = -0.10         # 默认止损-10%
    default_take_profit: float = 0.20        # 默认止盈+20%
    
    # 基准配置
    benchmark: str = '000300.SH'             # 基准指数（沪深300）
```

### 3. 信号数据格式

信号DataFrame必须包含以下列：

| 列名 | 类型 | 说明 | 必需 |
|------|------|------|------|
| `date` | datetime | 信号日期 | ✅ |
| `stock_code` | str | 股票代码 | ✅ |
| `signal_type` | str | 信号类型（如momentum/reversal） | ✅ |
| `weight` | float | 信号权重（0-1），默认1.0 | ❌ |

### 4. 价格数据格式

价格数据为字典，键为股票代码，值为DataFrame，必须包含：

| 列名 | 类型 | 说明 |
|------|------|------|
| `trade_date` 或 `date` | datetime | 交易日期 |
| `open` | float | 开盘价 |
| `close` | float | 收盘价 |

## 回测结果

### 收益指标

- 总收益率
- 年化收益率
- 基准收益率
- 超额收益

### 风险指标

- 最大回撤
- 波动率
- 夏普比率（Sharpe Ratio）
- 索提诺比率（Sortino Ratio）
- 卡玛比率（Calmar Ratio）

### 交易指标

- 总交易数
- 胜率
- 盈亏比
- 平均持仓天数
- 平均收益/笔

## 与现有代码整合

### 陶博士策略示例

```python
# 使用现有的数据获取和指标计算
from strategist.doctor_tao.data_fetcher import DoctorTaoDataFetcher
from strategist.doctor_tao.indicators import IndicatorCalculator

# 获取数据
fetcher = DoctorTaoDataFetcher()
price_dict = fetcher.fetch_daily_price_batch(stock_codes, start_date, end_date)

# 计算指标
price_df = pd.concat([df.assign(stock_code=code) for code, df in price_dict.items()])
indicators_df = IndicatorCalculator.calc_all_indicators(price_df)

# 生成信号
signals = indicators_df[
    (indicators_df['rps'] >= 90) & 
    (indicators_df['ma20'] > indicators_df['ma60'])
].copy()
signals['signal_type'] = 'momentum'
signals['date'] = signals['trade_date']

# 运行回测
engine = BacktestEngine(config)
result = engine.run(signals, price_dict)
```

## 架构说明

```
strategist/backtest/
├── __init__.py          # 模块导出
├── config.py            # 配置类
├── portfolio.py         # 组合管理（持仓、交易）
├── engine.py            # 回测引擎
├── metrics.py           # 指标计算
└── report.py            # 报告生成
```

### 核心流程

1. **初始化**：创建配置、组合管理器
2. **逐日遍历**：
   - 更新持仓市值
   - 检查退出条件（止损/止盈/到期）
   - 处理新信号（买入）
   - 记录每日净值
3. **计算指标**：收益、风险、交易统计
4. **生成报告**：Markdown + CSV

## 进阶功能

### 自定义仓位管理

```python
# 等权重（默认）
config.position_sizing = 'equal'

# 风险平价（TODO）
config.position_sizing = 'risk_parity'

# 凯利公式（TODO）
config.position_sizing = 'kelly'
```

### 自定义退出条件

可以通过修改 `Position` 类的参数来自定义每只股票的退出条件：

```python
# 在信号生成时指定
position.stop_loss = -0.15      # 止损-15%
position.take_profit = 0.30     # 止盈+30%
position.target_hold_days = 90  # 持仓90天
```

## 注意事项

1. **数据对齐**：确保价格数据和信号数据的日期能够对齐
2. **未来函数**：信号日期应该是T日，回测会在T+1日执行（使用T+1日收盘价）
3. **资金不足**：当资金不足时，会跳过该信号
4. **持仓限制**：达到最大持仓数时，不再接受新信号

## 示例脚本

参考 `strategist/doctor_tao/run_backtest_new.py` 查看完整示例。

## TODO

- [ ] 支持做空
- [ ] 风险平价仓位管理
- [ ] 凯利公式仓位管理
- [ ] 可视化（净值曲线、回撤图）
- [ ] 分年度统计
- [ ] 滚动回测
