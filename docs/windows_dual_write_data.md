# Windows 端双写数据表总览

## 概述

以下数据表由 Windows 端通过 QMT 及外部数据源拉取，同时写入本地数据库 (192.168.97.1) 和阿里云数据库 (123.56.3.1)，实现双端数据同步。

---

## 一、Windows 端数据拉取 (QMT + 外部数据源)

这些任务运行在 Windows 服务器上，依赖 QMT 客户端或网络数据源。

### 1.1 日线行情数据 (每日)

| 表名 | 数据内容 | 关键字段 | 数据来源 | 运行方式 |
|------|---------|---------|---------|---------|
| trade_stock_daily | A股日线行情 | 股票代码、交易日期、开高低收、成交量、成交额、换手率 | QMT xtdata | 每日盘后自动 |
| trade_etf_daily | ETF日线行情 | 基金代码、交易日期、开高低收、成交量、成交额 | QMT xtdata | 每日盘后自动 |
| trade_hk_daily | 港股日线行情 | 股票代码、交易日期、开高低收、成交量、成交额、换手率 | QMT xtdata | 每日盘后自动 |

### 1.2 财务与估值数据 (每日/每季度)

| 表名 | 数据内容 | 关键字段 | 数据来源 | 运行方式 |
|------|---------|---------|---------|---------|
| trade_stock_financial | A股财务指标 | 股票代码、报告期、营收、净利润、EPS、ROE、ROA、毛利率、净利率、资产负债率、流动比率、经营现金流、总资产、净资产 | QMT 财务报表 | 每季度财报发布后 |
| trade_stock_daily_basic | A股每日估值 | 股票代码、交易日期、总市值、流通市值、PE(TTM)、PB、PS(TTM)、股本等 | 百度股市通 (akshare) | 每日盘后自动 |

### 1.3 数据库配置

Windows 端 `.env` 配置:

```bash
DB_ENV=online
DUAL_WRITE=true
DUAL_WRITE_TARGET=local

# 阿里云 (主库)
ONLINE_DB_HOST=123.56.3.1
ONLINE_DB_PORT=3306
ONLINE_DB_USER=quant_user
ONLINE_DB_PASSWORD=Quant@2024User
ONLINE_DB_NAME=wucai_trade

# 本地 (副库)
LOCAL_DB_HOST=192.168.97.1
LOCAL_DB_PORT=3306
LOCAL_DB_USER=quant_user
LOCAL_DB_PASSWORD=Quant@2024User
LOCAL_DB_NAME=wucai_trade
```

---

## 二、Mac 端数据计算任务 (已支持双写)

这些任务运行在 Mac 端 (192.168.97.1)，读取数据库中的行情数据，计算因子/指标后写回数据库。均已改造为双写。

### 2.1 每日计算任务

| 任务 | 模块 | 写入表 | 数据内容 | 运行命令 |
|------|------|--------|---------|---------|
| 宏观数据拉取 | data_analyst/fetchers/macro_fetcher.py | macro_data | WTI油价、黄金、中国VIX、北向资金 | `python daily_run.py` (step1) |
| 宏观因子计算 | data_analyst/factors/macro_factor_calculator.py | macro_factors | oil_mom_20, gold_mom_20, vix_ma5 | `python daily_run.py` (step2) |
| RPS 增量更新 | data_analyst/indicators/rps_calculator.py | trade_stock_rps | rps_20/60/120/250, rps_slope | `python -m data_analyst.indicators.rps_calculator --latest` |
| SVD 市场监控 | data_analyst/market_monitor/run_monitor.py | trade_svd_market_state | top1/3/5方差比、重构误差、市场状态、突变标记 | `python -m data_analyst.market_monitor.run_monitor --latest` |
| Log Bias 计算 | strategist/log_bias/ | trade_log_bias_daily | ln_close, ema_ln_20, log_bias, signal_state | 策略模块内部调用 |
| 因子有效性验证 | data_analyst/factors/factor_validator.py | trade_factor_validation | factor_name, ic_mean, icir, is_valid | `python data_analyst/factors/factor_validator.py` (手动) |

### 2.2 因子批量计算 (每日/手动回填)

以下因子表依赖 trade_stock_daily 数据就绪后计算:

| 任务 | 模块 | 写入表 | 因子列表 | 运行命令 |
|------|------|--------|---------|---------|
| 基础因子 | data_analyst/factors/basic_factor_calculator.py | trade_stock_basic_factor | mom_20, mom_60, reversal_5, turnover, vol_ratio, price_vol_diverge, volatility_20 | `python data_analyst/factors/basic_factor_calculator.py` |
| 扩展因子 | data_analyst/factors/extended_factor_calculator.py | trade_stock_extended_factor | mom_5, mom_10, reversal_1, turnover_20_mean, amihud_illiquidity, high_low_ratio, volume_ratio_20, roe_ttm, gross_margin, net_profit_growth, revenue_growth | `python data_analyst/factors/extended_factor_calculator.py` |
| 估值因子 | data_analyst/factors/valuation_factor_calculator.py | trade_stock_valuation_factor | pe_ttm, pb, ps_ttm, market_cap, circ_market_cap | `python data_analyst/factors/valuation_factor_calculator.py` |
| 质量因子 | data_analyst/factors/quality_factor_calculator.py | trade_stock_quality_factor | cash_flow_ratio, accrual, current_ratio, roa, debt_ratio | `python data_analyst/factors/quality_factor_calculator.py` |
| 技术因子 (TA-Lib) | data_analyst/factors/factor_calculator.py | trade_stock_factor | momentum_20d/60d, volatility, rsi_14, adx_14, turnover_ratio, price_position, macd_signal | `python -c "from data_analyst.indicators.technical import TechnicalIndicatorCalculator; ..."` |
| 因子回填 | data_analyst/factors/backfill_factors.py | trade_stock_basic_factor | 同基础因子 | `python data_analyst/factors/backfill_factors.py` (手动) |

### 2.3 每周/不定期任务

| 任务 | 模块 | 写入表 | 数据内容 | 运行方式 |
|------|------|--------|---------|---------|
| 行业分类更新 | strategist/multi_factor/industry_fetcher.py | trade_stock_basic.industry | 东方财富行业板块一级分类 | 手动 `python -m strategist.multi_factor.industry_fetcher` |
| 财务数据拉取 | data_analyst/financial_fetcher/ | financial_income, financial_balance, financial_dividend, bank_asset_quality | 利润表、资产负债表、分红记录、银行资产质量 | 每季度财报发布后手动 |
| 模拟交易信号 | strategist/xgboost_strategy/paper_trading/ | pt_rounds, pt_positions | 每周五生成信号，每日结算 | 周五信号 + 每日结算 |
| 技术指标扫描 | data_analyst/indicators/technical.py | trade_technical_indicator | ma, macd, rsi, kdj, boll, atr | 手动 |
| 因子滚动IC监控 | research/factor_monitor.py | factor_alerts, factor_status | 因子IC衰减监控 | `python daily_run.py` (step3) |

### 2.4 定时调度 (scheduler_service.py)

通过 `python -m data_analyst.services.scheduler_service` 启动:

| 时间 | 任务 | 说明 |
|------|------|------|
| 18:00 | 数据完整性检查 + 触发因子计算 | 检查 trade_stock_daily 是否更新到最新交易日 |
| 18:30 | SVD 市场状态监控 | 计算当日市场状态 |

---

## 三、数据依赖链

```
Windows (每日盘后)                    Mac (每日/计算)
====================                  ================

QMT xtdata --------+                  +---> 基础因子 (basic_factor)
                   |                  +---> 扩展因子 (extended_factor)
                   v                  +---> 估值因子 (valuation_factor)
          trade_stock_daily -------->+---> 质量因子 (quality_factor)
                   |                  +---> 技术因子 (trade_stock_factor)
                   |                  +---> RPS (trade_stock_rps)
                   |                  +---> Log Bias (trade_log_bias_daily)
                   |                  +---> 技术指标 (trade_technical_indicator)
                   |
akshare ----------+---> trade_stock_daily_basic
                   |
QMT 财务 --------+---> trade_stock_financial --+---> 扩展因子中的财务字段
                                              +---> 质量因子

macro_fetcher ----+---> macro_data ---------->+---> macro_factors
```

**关键依赖**: Mac 端所有因子计算都依赖 trade_stock_daily 数据先就绪。Windows 端 QMT 拉取完成后，Mac 端才能开始计算。

---

## 四、双写状态总览

### 已支持双写 (DUAL_WRITE=true 时自动生效)

| 表名 | 写入模块 | 状态 |
|------|---------|------|
| macro_data | macro_fetcher.py | 已支持 |
| macro_factors | macro_factor_calculator.py | 已支持 |
| trade_stock_rps | rps_calculator.py | 已支持 |
| trade_svd_market_state | market_monitor/storage.py | 已支持 |
| trade_stock_basic_factor | basic_factor_calculator.py | 已支持 |
| trade_stock_extended_factor | extended_factor_calculator.py | 已支持 |
| trade_stock_valuation_factor | valuation_factor_calculator.py | 已支持 |
| trade_stock_quality_factor | quality_factor_calculator.py | 已支持 |
| trade_stock_factor | factor_storage.py | 已支持 |
| trade_factor_validation | factor_validator.py | 已支持 |
| trade_log_bias_daily | log_bias/storage.py | 已支持 |
| trade_stock_basic.industry | multi_factor/industry_fetcher.py | 已支持 |
| financial_income/balance/dividend/bank_asset_quality | financial_fetcher/storage.py | 已支持 |
| trade_stock_daily_basic | daily_basic_fetcher.py | 已支持 |

### 未改造 (Windows 端独立写入, 不需要双写)

| 表名 | 写入模块 | 原因 |
|------|---------|------|
| trade_stock_daily | qmt_fetcher.py | Windows 端 QMT 独立双写 |
| trade_etf_daily | etf_fetcher.py | Windows 端 QMT 独立双写 |
| trade_hk_daily | qmt_fetcher.py | Windows 端 QMT 独立双写 |
| trade_stock_financial | Windows 端 | Windows 端 QMT 独立双写 |
| trade_technical_indicator | technical.py | Mac 端单写, 未改造 |
| pt_rounds / pt_positions | paper_trading/ | 模拟交易状态, 仅需本地 |

---

## 五、数据量级参考

| 表名 | 预估行数 | 增量频率 | 写入端 |
|------|---------|---------|-------|
| trade_stock_daily | 数千万级 | 每日 ~5000 只 | Windows |
| trade_etf_daily | 百万级 | 每日 ~800 只 | Windows |
| trade_hk_daily | 百万级 | 每日 ~2000 只 | Windows |
| trade_stock_financial | 百万级 | 每季度 | Windows |
| trade_stock_daily_basic | 数千万级 | 每日 ~5000 只 | Windows + Mac (双写) |
| trade_stock_basic_factor | 数千万级 | 每日 ~5000 只 | Mac (双写) |
| trade_stock_extended_factor | 数千万级 | 每日 ~5000 只 | Mac (双写) |
| trade_stock_valuation_factor | 数千万级 | 每日 ~5000 只 | Mac (双写) |
| trade_stock_quality_factor | 数千万级 | 每日 ~5000 只 | Mac (双写) |
| trade_stock_rps | 数千万级 | 每日 ~5000 只 | Mac (双写) |
| trade_stock_factor | 数千万级 | 每日 ~5000 只 | Mac (双写) |
| macro_data | 万级 | 每日 4 个指标 | Mac (双写) |
| macro_factors | 千级 | 每日 | Mac (双写) |
| trade_svd_market_state | 千级 | 每日 3 个窗口 | Mac (双写) |
| trade_log_bias_daily | 万级 | 每日 | Mac (双写) |
