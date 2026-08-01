# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 绝对禁止

- **禁止使用任何 emoji 字符**。代码、注释、报告、CSV、日志、Markdown 输出中一律不使用 emoji。原因：MySQL utf8 字符集不支持 4 字节 emoji，会导致写入失败。用纯文本标记替代（[RED]、[WARN]、[OK]、[BAD]、[CRITICAL]）。
- **禁止读取 docs/archive/ 下的任何文件**。这些是已过期的历史文档（旧 PRD、实施计划、设计方案），内容与当前代码不符，会误导你的判断。如需了解历史决策，用 `git log` 或 `git blame` 查看代码变更记录。

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
├── docs/             # ops/ 运维文档 | claude/ 领域文档 | archive/ 已归档(禁止读取)
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

### yfinance 本机抓取

阿里云 ECS 访问 Yahoo Finance 会被限流/封 IP。yfinance 相关数据（全球资产 + A 股指数 fallback）需要从**本机 macOS 抓取后写入线上数据库**：

```bash
# 手动同步所有 yfinance 指标
DB_ENV=online python scripts/yfinance_sync.py

# 只同步指定指标
DB_ENV=online python scripts/yfinance_sync.py --indicators ovx vix gvz idx_all_a

# 同步最近 30 天
DB_ENV=online python scripts/yfinance_sync.py --days 30
```

涉及指标: btc, brent_oil, spy, qqq, dia, vix, gvz, ovx, dxy, usdcny, idx_all_a, idx_sse, idx_csi300, idx_csi500。

本机 crontab 每日 07:30 (工作日) 自动执行。服务器上 `fetch_macro_data_hourly` 仍正常运行 AKShare 数据源，两者互补（`ON DUPLICATE KEY UPDATE`）。

## 代码规范 [CRITICAL]

> **确定性检查已脚本化**：下述 CRITICAL 规则（禁裸 getenv / SQL 占位符 / 枚举 key .value 等）
> 加 emoji、ruff、前端 tsc/eslint，由 `bash scripts/preflight.sh` 一次跑完、带证据、遇错不中断。
> 提交/提 MR 前 agent **先跑脚本拿结果**，不必逐条手动核对。默认只查【本次改动】（工作区未提交部分，
> 因本地直接提交到 main，不用 origin diff）。`--backend`/`--frontend`/`--quiet`/`--all` 见脚本头。
> pytest 未装时自动软跳过（`pip install -r requirements-dev.txt` 后启用）。
> 脚本不代劳的语义步骤：diff 每行可追溯 · **涉资金逻辑/migration 复核** · /code-review 拍板 · 部署问询。
> 设计出处：Kun Chen firstmate「脚本做结构、agent 做语义」。

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

## Remote Server Work

- SSH 执行复杂命令时，优先将脚本写到本地文件再 `scp` 上传执行，避免 heredoc 嵌套引号问题。
- 通过 SSH 隧道或远程连接查询数据库时，优先使用 Python（`pymysql`/`sqlalchemy`）而非在 shell 命令中嵌入原始 SQL，避免转义问题。

## 工作规范

### 协作风格
- **所有回复使用中文**。代码注释、变量名、commit message 可以用英文，但与用户的对话一律用中文。
- 用户说"do it"或给出简短确认时，直接执行最明显的下一步，不要反问可以推断的内容。
- **实现任何功能前，先列出：1) 计划修改的文件列表，2) 最小化方案描述。等待确认后再写代码。**
- 实现大功能前确认 scope：询问"要完整版还是精简版？"，不要默认做完整实现。

### 异步沟通与任务执行

任务文件位于 `/Users/zhaobo/Documents/notes/Daily/task/tasks_myTrader.md`，执行长任务（涉及 3+ 文件改动或预计 10+ 分钟）时遵守以下规则：

1. **定期回读**：每完成一个子步骤，回读任务文件，检查「待决策」区和「追加要求」区是否有新内容
2. **决策分级**：遇到红灯事项（涉及资金逻辑、数据库 migration、对外接口变更、生产部署）时，将问题写入任务文件的「待决策」区（附上选项和建议），然后跳过该步继续做其他子任务，不要停下来等
3. **进展更新**：DOING 状态的任务加 `进展：` 字段，每完成一个关键步骤更新一行，格式为 `- [时间] 做了什么`
4. **黄灯自主决策**：可逆操作（内部重构、UI 调整等）自行决策，在进展中记录决策理由

### Code Review
- 每次做 diff review 前必须重新运行 `git diff`（对准确的 branch/ref），禁止使用缓存或上次的 diff 结果。
- 二次 review 时，必须重新运行 diff，不假设上次结果仍然有效；明确对比上次结论，指出哪些问题已修复、哪些仍存在、哪些是新增。
- **对抗性审查纪律（学 Kun Chen no-mistakes：不同模型交叉，实测抓 63% 改动的错误）**：
  合并前必跑 `/code-review`，且**主动切换到「挑刺者」心态**——专门找边缘 case、罕见但会发生的场景、
  文档与代码不一致。**myTrader 涉资金逻辑，此步不可省**：仓位/下单/风控相关改动必须逐条对
  「资金安全」维度挑刺（越界买入、重复下单、风控绕过、精度丢失）。
- **有稳定的第二模型 CLI（codex/gemini/API）后**，把本步升级为双模型交叉审查并脚本化
  （`scripts/review-adversarial.sh`，接口可插拔）；当前 gemini 个人版已失效，暂用单模型 + 挑刺心态。

### 远程服务器操作
- 重新发送失败任务（如 Celery 任务）前，必须先确认新 worker 已启动完毕。

### 搜索与调试
- 主要语言：Python（后端/策略）、TypeScript（前端）。搜索 bug 时优先在这两类文件中定位。
- 搜索文件时用 Glob/Grep 而非凭记忆猜文件名，若文件不存在立即换方向，不要反复尝试。

## 任务收尾清单（每个开发任务提交前必过）

编码自测通过不等于任务完成。按序逐条过，不要跳步。

> **确定性步骤已脚本化**：第 1-3 步由 `bash scripts/preflight.sh` 一次跑完、带证据、遇错不中断。
> agent **先跑脚本拿结果**，不必逐条手动跑。脚本全绿后再做第 4-7 步的**语义判断**（脚本不代劳）。
> 参数：`--backend`/`--frontend` 分别跑，`--quiet` 省 token，`--all` 查全仓存量（一般不用）。
> 默认只查【本次改动】（工作区未提交部分，因本地直接提交到 main，不用 origin diff）。
> 设计出处：Kun Chen firstmate「脚本做结构、agent 做语义」。

1. **测试与收集**：本次改动相关的测试必须绿 + `python -m pytest tests/ --collect-only -q` 无收集错误
   （当前有 2 个收集 error，见 `docs/tech-debt.md` #5，清偿前以「相关目录绿」为过关线）
2. **规范检查**：ruff 无新增 error（棘轮式，只查本次改动）；CRITICAL 规则（禁裸 getenv / SQL 占位符 /
   枚举 key .value）由 `scripts/check_code_rules.py` 覆盖
3. **emoji 检查**：`python scripts/check_no_emoji.py`（MySQL utf8 不支持 4 字节 emoji）
4. **diff 自查**：重新 `git diff` 完整过一遍，每行改动可追溯到需求；确认没有偷偷加功能/重构/格式美化
5. **[myTrader 独有] 数据正确性复核** —— 涉及因子计算、策略信号、仓位/下单/风控的改动必须逐条核：
   - **前视偏差**：是否用到了当日或未来才能拿到的数据？滚动窗口的 shift 方向对不对？
   - **min_periods**：MA 类滚动指标 `min_periods` 是否设成了 `window`（不是 1）？
   - **复权一致性**：同一段计算里前复权/后复权/不复权是否混用？
   - **停牌与退市**：停牌日是否被当成有效交易日？退市股是否还在票池里？
   - **精度**：金额/份额计算是否用了 float 导致累积误差？涉资金必须 Decimal 或整数分。
   - **静默失败**：新增的 `except` 是否会把错误吞成一个「看起来正常」的空结果？
     （投研系统里静默失败比崩溃更糟——见 `docs/tech-debt.md` #9）
6. **对抗性 code-review**：跑 `/code-review`，主动切换「挑刺者」心态。
   **涉资金逻辑此步不可省**：越界买入、重复下单、风控绕过、精度丢失逐条挑。
   高置信 bug 直接修（修完回跑测试确认绿），可疑/PLAUSIBLE 项分级报给用户等拍板，
   **禁止自动 `--fix` 把不确定判断落进代码**。
7. **技术债回顾**（登记表 `docs/tech-debt.md`）：本次改动若触碰了登记项涉及的文件，顺手清偿并把条目
   移到「已清偿」（附日期）；发现新债务或明知欠债先上线的，**先登记再提交**，不允许「先欠着、口头记得」

> **部署是独立决策**：以上全绿只代表代码可提交。生产部署必须单独明确询问用户，不随改动一起执行。

## 领域文档

| 文档 | 内容 |
|------|------|
| [docs/claude/web_api.md](docs/claude/web_api.md) | Web 平台 & API 服务：路由、前端页、数据库表、Celery Beat 定时任务全览、环境变量、CI/CD |
| [docs/claude/xgboost_strategy.md](docs/claude/xgboost_strategy.md) | XGBoost 截面预测策略：52 维因子、滚动训练、IC 评估 |
| [docs/claude/svd_monitor.md](docs/claude/svd_monitor.md) | SVD 市场状态监控：多尺度窗口、突变检测、行业中性化 |
| [docs/claude/tech_scan.md](docs/claude/tech_scan.md) | 持仓技术面扫描：每日盘后扫描、分级预警、Backlog |
| [docs/claude/scheduler.md](docs/claude/scheduler.md) | 任务调度器：YAML DAG、数据监控服务、报警通知 |
| [docs/claude/factor_registry.md](docs/claude/factor_registry.md) | 因子与策略登记表：结构层(generated) + 语义层(manual，赚钱理由/失效触发条件) |
| [docs/tech-debt.md](docs/tech-debt.md) | 技术债登记：现状+影响+方向+日期，收尾清单第 7 步必过 |
