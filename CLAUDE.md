# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 绝对禁止

- **禁止使用任何 emoji 字符**。代码、注释、报告、CSV、日志、Markdown 输出中一律不使用 emoji。原因：MySQL utf8 字符集不支持 4 字节 emoji，会导致写入失败。用纯文本标记替代（如 [RED]、[WARN]、[OK]）。

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

# XGBoost 截面预测策略
python -m strategist.xgboost_strategy.test_strategy  # 测试模块
python -m strategist.xgboost_strategy.run_strategy   # 运行策略
```

## 项目结构

```
myTrader/
├── config/                    # 配置模块
│   ├── db.py                  # 数据库连接工具（支持双环境）
│   └── settings.py            # 全局配置
│
├── data_analyst/              # 数据分析师模块
│   ├── fetchers/              # 数据拉取器 (QMT/Tushare/AKShare)
│   ├── financial_fetcher/     # 财务数据拉取
│   ├── factors/               # 因子计算与存储
│   ├── indicators/            # 技术指标计算 (MA/MACD/RSI/KDJ/BOLL/ATR)
│   ├── market_monitor/        # SVD 市场状态监控
│   ├── services/              # 数据监控、报警、定时任务
│   └── sw_rotation/           # 申万行业轮动分析
│
├── strategist/                # 策略师模块
│   ├── backtest/              # 通用回测框架
│   ├── doctor_tao/            # 陶博士策略（RPS+动量）
│   ├── xgboost_strategy/      # XGBoost 截面预测策略
│   │   └── paper_trading/     # 模拟交易
│   ├── tech_scan/             # 持仓技术面扫描
│   ├── multi_factor/          # 多因子选股
│   ├── log_bias/              # 对数偏差策略
│   └── universe_scanner/      # 全市场扫描
│
├── risk_manager/              # 风控师模块
├── executor/                  # 交易员模块
├── investment_rag/            # 投研 RAG 系统
├── research/                  # 研究脚本（因子验证、ETF 回测等）
├── scripts/                   # 运维脚本
├── docs/                      # 文档与设计稿
│
├── output/                    # 统一输出目录（git ignored）
│   ├── doctor_tao/            # 陶博士策略产出
│   ├── xgboost/               # XGBoost 策略产出
│   ├── multi_factor/          # 多因子选股产出
│   ├── single_scan/           # 个股扫描产出
│   ├── svd_monitor/           # SVD 监控产出
│   ├── sw_rotation/           # 申万轮动产出
│   └── research/              # 研究脚本产出
│
├── .env                       # 环境配置 (不提交)
├── .env.example               # 环境配置模板
└── requirements.txt           # Python依赖
```

## 目录规范

### output 统一输出目录

所有模块的生成产物统一放到项目根目录的 `output/` 下，按模块分子目录。`output/` 已加入 `.gitignore`，不纳入版本控制。

```
output/
├── doctor_tao/       # strategist/doctor_tao/ 产出
├── xgboost/          # strategist/xgboost_strategy/ 产出
├── multi_factor/     # strategist/multi_factor/ 产出
├── single_scan/      # strategist/tech_scan/ 个股扫描产出
├── svd_monitor/      # data_analyst/market_monitor/ 产出
├── sw_rotation/      # data_analyst/sw_rotation/ 产出
├── log_bias/         # strategist/log_bias/ 产出
├── universe_scan/    # strategist/universe_scanner/ 产出
└── research/         # research/ 脚本产出
```

**路径写法规范**：

```python
import os
import sys

# 1. 在文件头部定义 ROOT（通过 __file__ 回溯到项目根目录）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 2. output 路径使用 ROOT 拼接
output_dir = os.path.join(ROOT, 'output', '<module_name>')
os.makedirs(output_dir, exist_ok=True)
```

**禁止事项**：
- 禁止使用 `os.path.join(os.path.dirname(__file__), 'output')` 在模块目录下创建 output
- 禁止使用裸相对路径如 `'output/xxx.png'`（依赖 CWD，不可移植）
- 禁止在 `strategist/`、`data_analyst/` 等子目录下创建 output 子目录
- 禁止将 output 下的文件提交到 git

### 包结构规范

每个 Python 子模块目录必须包含 `__init__.py`，确保可被正常 import。

```
data_analyst/
├── __init__.py
├── fetchers/__init__.py
├── indicators/__init__.py
├── factors/__init__.py
├── services/__init__.py
├── financial_fetcher/__init__.py
├── market_monitor/__init__.py
└── sw_rotation/__init__.py

strategist/
├── __init__.py
├── backtest/__init__.py
├── doctor_tao/__init__.py
├── xgboost_strategy/__init__.py
├── tech_scan/__init__.py
├── multi_factor/__init__.py
├── log_bias/__init__.py
└── universe_scanner/__init__.py
```

### 新模块添加清单

添加新模块时需完成以下步骤：

1. 创建模块目录及 `__init__.py`
2. output 路径使用 `os.path.join(ROOT, 'output', '<module_name>')`
3. 如需新的 output 子目录，在上方目录树和 `.gitignore` 的 `output/` 条目中补充说明（`output/` 通配符已覆盖所有子目录，无需额外添加）
4. 更新本文件的项目结构树

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

参考 `/Users/wenwen/data0/person/quant` 项目实现，数据拉取相关代码已复用。

---

## 数据拉取管理

### 数据源
- **QMT Fetcher**: 全量A股日线数据（需 Windows 服务器）
- **Tushare Fetcher**: 使用 Tushare API 拉取数据（需要 Token）
- **AKShare Fetcher**: 免费数据源，无需 Token

### 数据拉取管理服务
统一管理各数据源的拉取：

```python
from data_analyst.fetchers.data_fetch_manager import DataFetchManager, DataFetchResult

manager = DataFetchManager()

# 从 AKShare 拉取日线数据
result = manager.fetch_daily_data(DataFetcherType.AKSHARE)
```

### 数据监控服务
每天 18:00 自动检查数据完整性：

```python
from data_analyst.services.data_monitor import DataMonitor
from data_analyst.services.alert_service import AlertService
from data_analyst.services.scheduler_service import SchedulerService

# 检查数据
monitor = DataMonitor()
result = monitor.check_daily_data()

if result['is_ok']:
    print("数据正常，触发因子计算...")
else:
    print("数据异常，发送报警...")
```

### 定时任务
- **18:00**: 数据完整性检查，数据正常则触发因子计算
- 可自定义添加其他定时任务

```bash
# 启动定时任务调度器
python -m data_analyst.services.scheduler_service
```

### 报警通知
支持飞书 Webhook 推送，配置 `.env`:

```bash
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

---

## 代码规范与常见 Bug 注意事项

### 🔴 严重问题（必须避免）

#### 1. Python 语法错误
- **import 语句必须独立成行**，不要合并多个 import
  ```python
  # ❌ 错误
  from datetime import datetime,import sys
  from config.db import execute_query,from config.settings import settings
  
  # ✅ 正确
  from datetime import datetime
  import sys
  from config.db import execute_query
  from config.settings import settings
  ```

- **Python 关键字大小写敏感**
  ```python
  # ❌ 错误
  return none
  except exception as e:
  
  # ✅ 正确
  return None
  except Exception as e:
  ```

#### 2. SQL 语法错误
- **SQL 字段定义之间必须有逗号**
  ```sql
  -- ❌ 错误
  adx_14 DOUBLE COMMENT 'ADX'
  turnover_ratio DOUBLE COMMENT '换手率'
  
  -- ✅ 正确
  adx_14 DOUBLE COMMENT 'ADX',
  turnover_ratio DOUBLE COMMENT '换手率',
  ```

- **SQL VALUES 占位符数量必须与字段数量一致**
  ```python
  # 9 个字段必须对应 9 个 %s
  sql = """
      INSERT INTO table (f1, f2, f3, f4, f5, f6, f7, f8, f9)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
  """
  ```

#### 3. 枚举值大小写一致性
- 定义和使用必须完全一致
  ```python
  # 定义
  class FetcherType(Enum):
      QMT = "qmt"
      TUSHARE = "tushare"
      AKSHARE = "akshare"
  
  # ❌ 错误使用
  FetcherType.Qmt
  FetcherType.tushare
  
  # ✅ 正确使用
  FetcherType.QMT
  FetcherType.TUSHARE
  ```

#### 4. 字典 key 类型匹配
- 枚举作为字典 key 时，注意 `.value` 的使用
  ```python
  config = {'qmt': {...}, 'tushare': {...}}
  
  # ❌ 错误：ft 是枚举类型，config key 是字符串
  if ft in config:
  
  # ✅ 正确：使用 ft.value 获取字符串值
  if ft.value in config:
  ```

### 🟡 因子计算注意事项

#### 1. 滚动窗口 min_periods 设置
- **MA 等滚动指标**：`min_periods` 应设为 `window` 而非 `1`，避免前期数据失真
  ```python
  # ❌ 错误：前249天的MA250都是假值
  df['ma250'] = close.rolling(window=250, min_periods=1).mean()
  
  # ✅ 正确：数据不足时返回NaN
  df['ma250'] = close.rolling(window=250, min_periods=250).mean()
  ```

#### 2. 交易日与自然日转换
- 250 交易日 ≈ 365 自然日
  ```python
  # ❌ 错误：250自然日只有约170个交易日
  timedelta(days=250)
  
  # ✅ 正确：转换为自然日
  min_list_natural_days = int(min_list_days * 365 / 250)
  timedelta(days=min_list_natural_days)
  ```

#### 3. 缓存数据完整性检查
- 使用缓存前检查日期范围是否覆盖请求范围

### 🟢 代码风格

1. **import 语句放在文件顶部**，不要在函数内部重复 import
2. **避免硬编码文件路径**，使用 `glob` 或配置文件
3. **Decimal 类型转换**：数据库返回的 Decimal 类型需要转换为 float 才能与 numpy 运算

---

## Bug 修复记录

### 2026-03-26 data_analyst 模块修复

| 文件 | 问题 | 影响 |
|------|------|------|
| `data_fetch_manager.py:20` | import 语法错误 | 🔴 模块无法导入 |
| `factor_storage.py:15` | import 语法错误 | 🔴 模块无法导入 |
| `factor_storage.py:39-42` | SQL 缺少逗号 | 🔴 建表失败 |
| `factor_storage.py:284` | `none` → `None` | 🔴 运行时错误 |
| `factor_storage.py:323` | `exception` → `Exception` | 🔴 运行时错误 |
| `data_fetch_manager.py:72,97-99` | 枚举值大小写错误 | 🔴 AttributeError |
| `data_fetch_manager.py:76` | 字典 key 类型错误 | 🔴 KeyError |
| `data_fetch_manager.py:341,379` | SQL VALUES 参数不匹配 | 🔴 数据插入失败 |
| `technical.py:323` | SQL VALUES 参数不匹配 | 🔴 数据插入失败 |

### 2026-03-26 strategist/doctor_tao 模块修复

| 文件 | 问题 | 影响 |
|------|------|------|
| `indicators.py:75` | MA `min_periods=1` | 🔴 前期因子失真 |
| `signal_screener.py:89` | 交易日/自然日混淆 | 🟡 过滤条件过松 |
| `run_backtest_new.py:56` | 硬编码文件路径 | 🟡 文件不存在时报错 |
| `data_fetcher.py:103-109` | 缓存日期范围未检查 | 🟡 可能返回不完整数据 |

---

## XGBoost 截面预测策略

### 2026-03-27 新增模块

基于 MASTER 论文 (AAAI 2024) 思想，使用 XGBoost 进行股票截面预测的量化策略。

**核心特性**：
- **52 维技术因子** - 6 大类因子（价量、动量、波动率、技术指标、均线形态、交互）
- **截面预处理** - MAD 去极值 + Z-Score 标准化
- **滚动窗口训练** - XGBoost 模型滚动训练
- **IC 评估体系** - IC/ICIR/RankIC/RankICIR
- **完整回测框架** - 基于预测排名的选股回测

**模块结构**：
```
strategist/xgboost_strategy/
├── config.py              # 策略配置
├── feature_engine.py      # 52维因子计算引擎
├── preprocessor.py        # 截面预处理（MAD/Z-Score）
├── data_loader.py         # 数据加载与因子计算
├── model_trainer.py       # XGBoost滚动窗口训练
├── predictor.py           # 截面预测器
├── evaluator.py           # IC评估器
├── backtest.py            # 回测框架
├── visualizer.py          # 可视化工具
├── run_strategy.py        # 主入口脚本
├── test_strategy.py       # 测试脚本
└── README.md              # 详细文档
```

**快速开始**：
```bash
# 1. 安装依赖（必需）
pip install xgboost scipy scikit-learn
brew install ta-lib && pip install TA-Lib  # macOS

# 2. 测试模块
python -m strategist.xgboost_strategy.test_strategy

# 3. 运行策略
python -m strategist.xgboost_strategy.run_strategy
```

**输出结果**：
- `output/xgboost/signals.csv` - 每日预测信号
- `output/xgboost/portfolio_returns.csv` - 组合收益
- `output/xgboost/factor_ic.csv` - 因子 IC 统计
- `output/xgboost/ic_analysis.png` - IC 时序图和分布
- `output/xgboost/portfolio_performance.png` - 组合表现
- `output/xgboost/factor_ic.png` - 因子 IC 排名
- `output/xgboost/strategy_report.md` - 策略报告

**预期效果**：
- IC: 0.03~0.05
- ICIR: 0.3~0.5
- RankIC: 0.04~0.06

详见 `strategist/xgboost_strategy/README.md`

## SVD 市场状态监控

### 2026-03-29 新增模块

基于滚动 SVD 分解全 A 股收益率矩阵，监控市场因子结构变化。

**核心特性**：
- **多尺度窗口** - 20日/60日/120日三窗口并行监控
- **Randomized SVD** - 仅提取前 10 成分，极速计算
- **突变检测** - 短窗口偏离 2σ 自动触发警报 + 3 日冷却期
- **行业中性化** - 可选开关，适配择时/选股不同场景
- **重构误差** - Top5 因子解释不了的部分 = 市场混沌度

**模块结构**：
```
data_analyst/
└── market_monitor/
    ├── config.py              # 监控参数配置
    ├── schemas.py             # Pydantic 数据模型 + DDL
    ├── data_builder.py        # 收益率矩阵构建 + 预处理
    ├── svd_engine.py          # Randomized SVD 引擎
    ├── regime_classifier.py   # 市场状态分类 + 突变检测
    ├── storage.py             # 数据库读写层
    ├── visualizer.py          # 多尺度可视化
    ├── reporter.py            # Markdown 报告生成
    └── run_monitor.py         # 主入口 + CLI
```

**快速开始**：
```bash
# 仅计算最新状态
python -m data_analyst.market_monitor.run_monitor --latest

# 回填历史数据
python -m data_analyst.market_monitor.run_monitor --start 2025-01-01 --end 2026-03-28

# 开启行业中性化
python -m data_analyst.market_monitor.run_monitor --latest --industry-neutral
```

**输出结果**：
- `output/svd_monitor/svd_market_regime.png` - 多尺度监控图
- `output/svd_monitor/svd_report_YYYY-MM-DD.md` - 每日报告
- 数据库表 `trade_svd_market_state` - 历史数据

## 持仓技术面扫描

### 2026-03-30 新增模块

每日盘后自动扫描持仓股票的技术面状态，生成 Markdown 报告。

**核心特性**：
- **持仓解析** - 自动解析 Markdown 持仓文件，提取 A 股/ETF 代码
- **技术指标** - MA5/20/60/250、MACD、RSI、成交量比
- **信号检测** - 回踩/突破、金叉/死叉、超买/超卖、RPS 走弱
- **分级预警** - 🔴红灯/⚠️黄灯/🟢绿灯 三级预警
- **Backlog** - 自动记录数据缺失、计算失败等异常

**模块结构**：
```
strategist/tech_scan/
├── config.py              # 扫描配置
├── portfolio_parser.py    # 持仓文件解析
├── data_fetcher.py        # 数据库数据获取
├── indicator_calculator.py # 技术指标计算
├── signal_detector.py     # 信号检测逻辑
├── report_generator.py    # Markdown 报告生成
├── backlog_manager.py     # 异常记录管理
├── scheduler.py           # 定时调度
└── run_scan.py            # 主入口
```

**快速开始**：
```bash
# 手动执行扫描
python -m strategist.tech_scan.run_scan

# 指定日期扫描
python -m strategist.tech_scan.run_scan --date 2026-03-29

# 启动定时调度（每日 16:30）
python -m strategist.tech_scan.scheduler

# 立即执行一次
python -m strategist.tech_scan.scheduler --run-now
```

**输出结果**：
- `/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay/TechScan_YYYYMMDD.md` - 扫描报告
- `/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay/backlog.md` - 异常记录
- `output/tech_scan/scan_YYYYMMDD.log` - 执行日志

**配置文件**：
- 持仓文件: `/Users/zhaobo/Documents/notes/Finance/Positions/00-Current-Portfolio-Audit.md`
- 数据库环境: `online` (使用线上 MySQL)

详见 `docs/technical_scan_design.md`
