# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 绝对禁止

- **禁止使用任何 emoji 字符**。代码、注释、报告、CSV、日志、Markdown 输出中一律不使用 emoji。原因：MySQL utf8 字符集不支持 4 字节 emoji，会导致写入失败。用纯文本标记替代（[RED]、[WARN]、[OK]、[BAD]、[CRITICAL]）。

## 项目概述

myTrader 是一个 Python 量化交易助手，分为四大核心模块：
数据分析师 (data_analyst) / 策略师 (strategist) / 风控师 (risk_manager) / 交易员 (executor)。
另有统一任务调度器 `scheduler/`（YAML DAG）、FastAPI Web API、Next.js 前端、投研 RAG 系统。

## 常用命令

```bash
# 环境初始化
pip install -r requirements.txt && cp .env.example .env

# 测试数据库连接
python -c "from config.db import test_connection; print(test_connection())"

# 数据拉取
python data_analyst/fetchers/tushare_fetcher.py

# API 服务
make api-local                  # 本地启动
make dev                        # Docker 启动 (Redis + API + Nginx)
make migrate                    # 数据库迁移

# 技术面扫描（每日盘后）
python -m strategist.tech_scan.run_scan

# 任务调度
python -m scheduler run all --tag daily
python -m scheduler summary

# 智能研报
DB_ENV=online python -m investment_rag.run_report --help

# 舆情监控
python -m data_analyst.sentiment.run_monitor --help
```

## 项目结构（骨架）

```
myTrader/
├── config/           # db.py (双环境连接) + settings.py
├── api/              # FastAPI: routers/ middleware/ models/ schemas/ services/ tasks/
├── alembic/          # 数据库迁移脚本
├── data_analyst/     # fetchers/ indicators/ factors/ market_monitor/ sentiment/ sw_rotation/
├── strategist/       # backtest/ doctor_tao/ xgboost_strategy/ tech_scan/ multi_factor/
├── risk_manager/
├── executor/
├── investment_rag/   # report_engine/ ingest/ retrieval/ embeddings/
├── scheduler/        # cli.py dag.py executor.py state.py
├── tasks/            # YAML 任务定义 (_base / 02_macro / 03_factors / 04_indicators / 05_strategy)
├── web/              # Next.js 16: src/app/ src/components/ src/lib/
├── tests/            # unit/ e2e/ load/ security/
├── docs/             # 文档（含 docs/claude/ 领域文档）
├── output/           # 统一输出目录（git ignored）
├── docker-compose.yml / Dockerfile / nginx.conf / Makefile
└── .env / .env.example / requirements.txt
```

## 目录规范

- **output/ 统一输出**：所有产物写入 `os.path.join(ROOT, 'output', '<module_name>')`，禁止在子模块目录下建 output/，禁止提交 output/ 内容。
- **ROOT 定义**：`ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`
- **包结构**：每个 Python 子模块目录必须包含 `__init__.py`。
- **新模块清单**：创建目录 + `__init__.py`，output 路径用 ROOT 拼接，更新本文档结构树。

## 架构要点

### 数据流
```
数据源(QMT/Tushare/AKShare) -> MySQL -> 技术指标/因子 -> 策略信号 -> 风控检查 -> 交易执行
```

### 双环境数据库

```python
from config.db import get_connection, get_online_connection, execute_query

conn = get_connection()                                           # 默认 DB_ENV
results = execute_query("SELECT ...", env='online')              # 显式指定
```

`.env` 关键配置：`DB_ENV=local`，`LOCAL_DB_*` / `ONLINE_DB_*` 分别配置本地和线上。

## 代码规范 [CRITICAL]

### Python 语法
- import 语句必须独立成行，不能合并
- 关键字大小写敏感：`None` / `Exception`，不是 `none` / `exception`

### SQL 语法
- 字段定义之间必须有逗号
- `VALUES` 占位符数量必须与字段数量严格一致

### 枚举与字典 key
- 枚举定义和使用大小写必须完全一致（`FetcherType.QMT` 非 `FetcherType.Qmt`）
- 枚举作为 dict key 时用 `.value` 获取字符串：`ft.value in config`

### 因子计算 [WARN]
- MA 滚动指标：`min_periods` 设为 `window`，不要设 `1`（避免前期数据失真）
- 250 交易日 ≈ 365 自然日，不要混淆

## 领域文档

| 文档 | 内容 |
|------|------|
| [docs/claude/web_api.md](docs/claude/web_api.md) | Web 平台 & API 服务：40 路由、11 前端页、6 数据库表、环境变量、CI/CD |
| [docs/claude/xgboost_strategy.md](docs/claude/xgboost_strategy.md) | XGBoost 截面预测策略：52 维因子、滚动训练、IC 评估 |
| [docs/claude/svd_monitor.md](docs/claude/svd_monitor.md) | SVD 市场状态监控：多尺度窗口、突变检测、行业中性化 |
| [docs/claude/tech_scan.md](docs/claude/tech_scan.md) | 持仓技术面扫描：每日盘后扫描、分级预警、Backlog |
| [docs/claude/scheduler.md](docs/claude/scheduler.md) | 任务调度器：YAML DAG、数据监控服务、报警通知 |
