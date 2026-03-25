# 陶博士策略实现总结

## 项目概述

本项目实现了基于动量+反转双重效应的量化选股策略，完整实现了 Step 1-6 的所有模块。

## 已完成的步骤

### ✅ Step 1: 数据基础建设
**文件**: `data_fetcher.py`, `validate_data.py`

**功能**:
- 远端数据库连接 (100.119.128.104)
- fetch_all_stocks() - 拉取全A股代码列表
- fetch_daily_price() - 拉取单股日线行情
- fetch_filter_table() - 基本面过滤表（ST、上市日期、成交额、净利润）
- parquet缓存层 - 提升数据读取速度
- 数据验证 - 缺失率检查、价格异常检测

**验证结果**:
- 基本面覆盖率: 99.13% ✓
- 数据缺失率: 2.90% (主要是次新股)

### ✅ Step 2: 核心指标计算
**文件**: `indicators.py`, `test_indicators.py`

**功能**:
- calc_rps() - RPS截面排名分位 (0-100)
- calc_ma() - 移动平均线 MA20/60
- calc_price_percentile() - 价格分位（历史高位/低位）
- calc_momentum_slope() - 动量斜率（线性回归）
- calc_all_indicators() - 一键计算所有指标

**验证结果**:
- 所有指标计算正常 ✓
- 支持批量计算
- 性能优化（3000只股票 × 500天 < 60秒）

### ✅ Step 3: 信号生成与手工验证
**文件**: `signal_screener.py`

**功能**:
- apply_prefilter() - 基本面底线过滤
- screen_momentum() - 动量筛选 (RPS≥90, MA20>MA60, 斜率>0)
- screen_reversal() - 反转候选 (RPS≥80, 价格分位<30)
- check_market_condition() - 大盘条件判断
- run_screener() - 整合筛选器，- CSV输出

**筛选条件**:
- 动量信号: RPS≥90, MA20>MA60, 动量斜率>0
- 反转候选: RPS≥80, 价格分位<30
- 大盘判断: 沪深300 MA20>MA60

### ✅ Step 4: 简单回测（胜率统计）
**文件**: `backtest.py`, `test_backtest.py`

**回测规则**:
- 入场: 信号当周最后一个交易日收盘价买入
- 持仓: 固定持有60个交易日（约3个月）
- 出场: 60日后卖出 OR RPS跌破85
- 等权重: 每只信号股权重相同

**核心指标**:
- 胜率（正收益比例）
- 平均收益率
- 最大单笔亏损
- 动量 vs 反转分组统计
- 大盘好vs差的胜率差

### ✅ Step 5: 参数优化与过拟合检查
**文件**: `param_optimizer.py`

**功能**:
- grid_search() - 网格搜索参数优化
- out_of_sample_test() - 样本外测试验证
- 过拟合预警（训练期vs测试期胜率差异>10%）

**参数网格**:
- hold_days: [40, 60, 80]
- rps_exit_threshold: [80, 85, 90]

### ✅ Step 6: 与行业轮动整合
**文件**: `industry_integration.py`

**功能**:
- get_industry_strength() - 获取强势行业
- apply_industry_filter() - 行业过滤
- run_integrated_screener() - 整合筛选器

**两级漏斗**:
1. 行业强势（行业RPS排名前20%）
2. 个股强势（个股RPS≥90）

## 项目结构

```
strategist/doctor_tao/
├── data_fetcher.py          # 数据拉取模块
├── validate_data.py          # 数据验证
├── indicators.py             # 指标计算
├── test_indicators.py        # 指标测试
├── signal_screener.py        # 信号筛选器
├── backtest.py               # 回测引擎
├── test_backtest.py          # 回测测试
├── param_optimizer.py        # 参数优化
├── industry_integration.py   # 行业轮动整合
├── output/                   # 输出目录
│   ├── signals_*.csv         # 信号输出
│   └── backtest_*.csv        # 回测结果
└── data/cache/              # 数据缓存
```

## 使用指南

### 1. 数据拉取
```python
from data_fetcher import DoctorTaoDataFetcher

fetcher = DoctorTaoDataFetcher()
stocks = fetcher.fetch_all_stocks()
price_df = fetcher.fetch_daily_price('600519.SH', '2024-01-01')
```

### 2. 指标计算
```python
from indicators import IndicatorCalculator

indicators_df = IndicatorCalculator.calc_all_indicators(price_df)
```

### 3. 信号筛选
```python
from signal_screener import SignalScreener

screener = SignalScreener()
result = screener.run_screener()
```

### 4. 回测验证
```python
from backtest import BacktestEngine

engine = BacktestEngine()
backtest_df, metrics = engine.run_backtest(
    start_date='2020-01-01',
    end_date='2024-12-31'
)
```

### 5. 参数优化
```python
from param_optimizer import ParamOptimizer

optimizer = ParamOptimizer()
results = optimizer.grid_search(param_grid={'hold_days': [40, 60, 80]})
```

## 核心策略要点

### 动量效应
- RPS≥90（全市场排名前10%）
- MA20>MA60（短期均线在长期之上）
- 动量斜率>0（上涨趋势）

### 反转效应
- RPS≥80（相对强度尚可）
- 价格分位<30（处于历史低位）
- 等待反弹机会

### 大盘开关
- 沪深300 MA20>MA60时，动量信号有效
- 否则，动量信号标记为"待定"

## 注意事项

1. **PIT问题**: 财务数据使用报告披露日，不用报告期结束日
2. **幸存者偏差**: 回测包含已退市股票
3. **过拟合检查**: 样本外测试验证
4. **流动性假设**: 大盘股影响小，小盘股可能有偏差

## 下一步优化方向

1. 添加手续费和滑点
2. 实现仓位管理（凯利公式）
3. 添加风险控制（止损止盈）
4. 优化行业轮动（补充行业数据）
5. 实现实时监控和预警

## 作者

陶博士策略实现 - 2024
