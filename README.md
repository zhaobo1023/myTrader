# myTrader - Python 量化交易助手

一个模块化的 Python 量化交易系统，支持数据采集、策略回测、风控管理和实盘交易。

## 项目结构

```
myTrader/
├── config/                    # 配置模块
│   ├── db.py                  # 数据库连接工具（支持双环境）
│   ├── settings.py            # 全局配置
│   └── models.py              # 数据库模型定义
│
├── data_analyst/              # 数据分析师模块
│   ├── fetchers/              # 数据拉取器
│   │   ├── qmt_fetcher.py     # QMT数据拉取 (全量A股)
│   │   └── tushare_fetcher.py # Tushare数据拉取
│   ├── processors/            # 数据清洗
│   └── indicators/            # 技术指标计算
│       └── technical.py       # MA/MACD/RSI/KDJ/BOLL/ATR
│
├── strategist/                # 策略师模块
│   ├── backtest/              # 回测框架
│   └── signals/               # 信号生成
│
├── risk_manager/              # 风控师模块
│   └── 风控规则实现
│
├── executor/                  # 交易员模块
│   ├── qmt/                   # QMT交易接口
│   └── orders/                # 订单管理
│
├── utils/                     # 通用工具
├── .env                       # 环境配置 (不提交)
├── .env.example               # 环境配置模板
└── requirements.txt           # Python依赖
```

## 核心模块

### 1. 数据分析师 (data_analyst)
- 支持多数据源：QMT (全量A股)、Tushare
- 多线程并行数据采集
- 增量更新机制
- 技术指标计算：MA、MACD、RSI、KDJ、布林带、ATR

### 2. 策略师 (strategist)
- 策略基类和模板
- 回测框架支持
- 信号生成器

### 3. 风控师 (risk_manager)
- 仓位管理
- 止损止盈
- 风险监控

### 4. 交易员 (executor)
- QMT 实盘接口
- 订单管理

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填写数据库配置
```

### 3. 数据采集

```bash
# 使用 QMT 拉取全量 A 股数据
python data_analyst/fetchers/qmt_fetcher.py

# 或使用 Tushare
python data_analyst/fetchers/tushare_fetcher.py
```

### 4. 计算技术指标

```python
from data_analyst.indicators.technical import TechnicalIndicatorCalculator

calculator = TechnicalIndicatorCalculator()
calculator.calculate_for_all_stocks()
```

## 双环境配置

项目支持本地和线上两套数据库环境：

```python
from config.db import get_connection, get_local_connection, get_online_connection

# 默认环境
conn = get_connection()

# 显式指定环境
conn = get_local_connection()   # 本地
conn = get_online_connection()  # 线上

# 执行查询时指定环境
from config.db import execute_query
results = execute_query("SELECT * FROM trade_stock_daily LIMIT 10", env='online')
```

环境配置在 `.env` 文件中：

```bash
DB_ENV=local                    # 当前环境: local 或 online

# 本地数据库
LOCAL_DB_HOST=localhost
LOCAL_DB_NAME=mytrader
...

# 线上数据库
ONLINE_DB_HOST=your_server
ONLINE_DB_NAME=trade
...
```

## 数据库表结构

| 表名 | 用途 |
|-----|------|
| trade_stock_daily | 日K线数据 (OHLCV) |
| trade_stock_daily_basic | 每日指标 (市值/PE/PB) |
| trade_stock_moneyflow | 资金流向 |
| trade_stock_financial | 财务数据 |
| trade_technical_indicator | 技术指标 |
| trade_stock_factor | 因子数据 |
| model_trade_position | 持仓管理 |

## 环境要求

- Python 3.10+
- MySQL 数据库
- (可选) QMT 客户端 - 用于数据拉取和实盘交易
- (可选) TA-Lib - 高性能技术指标计算

## License

MIT
