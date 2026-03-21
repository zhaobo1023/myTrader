# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

myTrader 是一个 Python 量化交易助手项目，分为四大核心模块：

1. **数据分析师 (data_analyst)** - 管理数据拉取、数据清洗、技术指标计算
2. **策略师 (strategist)** - 交易策略实现、策略回测、信号生成
3. **风控师 (risk_manager)** - 持仓风控管理、止损止盈、仓位控制
4. **交易员 (executor)** - QMT量化交易接口、订单管理

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 复制环境配置文件并填写配置
cp .env.example .env

# 数据拉取 - 使用QMT (推荐，全量A股数据)
python data_analyst/fetchers/qmt_fetcher.py

# 数据拉取 - 使用Tushare (需要TUSHARE_TOKEN)
python data_analyst/fetchers/tushare_fetcher.py

# 计算技术指标
python -c "from data_analyst.indicators.technical import TechnicalIndicatorCalculator; TechnicalIndicatorCalculator().calculate_for_all_stocks()"

# 测试数据库连接
python -c "from config.db import test_connection; print(test_connection())"
```

## 项目结构

```
myTrader/
├── config/                    # 配置模块
│   ├── db.py                  # 数据库连接工具（支持双环境）
│   └── settings.py            # 全局配置
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

## 架构要点

### 数据流
```
数据源(QMT/Tushare) -> MySQL -> 技术指标计算 -> 策略信号 -> 风控检查 -> 交易执行
```

### 双环境数据库配置

项目支持 **本地** 和 **线上** 两套数据库环境：

- **本地环境 (LOCAL_*)**: 用于开发和测试
- **线上环境 (ONLINE_*)**: 从原 quant 项目迁移的生产数据

**使用方式：**

```python
from config.db import get_connection, get_local_connection, get_online_connection

# 默认使用 DB_ENV 指定的环境（默认 local）
conn = get_connection()

# 显式指定本地环境
conn = get_local_connection()

# 显式指定线上环境
conn = get_online_connection()

# 在执行函数时指定环境
from config.db import execute_query, execute_many
results = execute_query("SELECT * FROM trade_stock_daily LIMIT 10", env='online')
```

**切换环境：**

```python
from config.db import switch_env, get_current_env

# 查看当前环境
print(get_current_env())  # 'local' 或 'online'

# 切换到线上环境
switch_env('online')
```

**配置文件 (.env)：**

```bash
# 当前环境
DB_ENV=local

# 本地数据库
LOCAL_DB_HOST=localhost
LOCAL_DB_NAME=mytrader
...

# 线上数据库
ONLINE_DB_HOST=your_server
ONLINE_DB_NAME=trade
...
```

### 技术指标计算
- 优先使用 TA-Lib（需单独安装）
- 未安装时自动降级到 pandas 实现
- 支持批量计算所有股票的技术指标

### 数据拉取优化
- QMT Fetcher: 多线程并行下载（8线程）
- 增量更新：只下载缺失的日期数据
- 自动计算换手率

## 环境要求

- Python 3.10+
- MySQL 数据库（本地 + 线上两套环境）
- (可选) QMT客户端 - 用于本地数据拉取和实盘交易
- (可选) TA-Lib - 用于高性能技术指标计算

## 参考项目

参考 `/Users/zhaobo/data0/person/quant` 项目实现，数据拉取相关代码已复用。
