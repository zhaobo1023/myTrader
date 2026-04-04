# scheduler -- myTrader 统一任务调度器

YAML 驱动的 DAG 任务调度系统，替代散落在 `daily_run.py`、`scheduler_service.py` 和各手动脚本中的任务管理。

## 快速开始

```bash
# 1. 安装依赖
pip install pyyaml

# 2. 查看 help
python -m scheduler --help

# 3. 列出所有任务
python -m scheduler list

# 4. dry-run 全部 daily 任务（不执行，只打印）
python -m scheduler run all --tag daily --dry-run
```

## CLI 命令

### list -- 列出任务

```bash
# 列出所有已注册的任务
python -m scheduler list

# 按标签过滤
python -m scheduler list --tag daily
python -m scheduler list --tag manual
python -m scheduler list --tag factor
python -m scheduler list --tag indicator
```

输出示例：

```
ID                             Name                 Tags                 Enabled  Depends
----------------------------------------------------------------------------------------------------
fetch_macro_data               Fetch macro indicators macro, daily         True
calc_macro_factors             Calculate macro factors macro, factor, daily True     fetch_macro_data
_gate_daily_price              Gate: wait for daily data gate, daily          True
...
```

### run -- 执行任务

```bash
# 全量 dry-run（推荐首次运行）
python -m scheduler run all --dry-run

# 按标签 dry-run
python -m scheduler run all --tag daily --dry-run

# 执行单个任务（dry-run）
python -m scheduler run fetch_macro_data --dry-run

# 执行单个任务（实际运行）
python -m scheduler run fetch_macro_data --env local

# 执行全部 daily 任务（实际运行）
python -m scheduler run all --tag daily --env online
```

当 `task_id` 不是 `all` 时，调度器会自动拉取该任务的完整依赖链。例如 `python -m scheduler run calc_factor_ic_monitor` 会先执行所有 factor 计算任务。

### status -- 查看任务历史

```bash
# 查看某任务的最近 10 次运行记录
python -m scheduler status fetch_macro_data --env local
```

需要数据库中有 `task_runs` 表（首次运行 `run` 时自动建表）。

### summary -- 今日执行摘要

```bash
python -m scheduler summary --env local
```

## 任务依赖 DAG

```
Batch 1 (无依赖):
  fetch_macro_data
  _gate_daily_price

Batch 2 (依赖 Batch 1):
  calc_macro_factors          <- fetch_macro_data
  calc_basic_factor           <- _gate_daily_price
  calc_valuation_factor       <- _gate_daily_price
  calc_quality_factor         <- _gate_daily_price
  calc_technical_factor       <- _gate_daily_price
  calc_rps                    <- _gate_daily_price
  calc_svd_monitor            <- _gate_daily_price
  calc_log_bias               <- _gate_daily_price
  calc_technical_indicator    <- _gate_daily_price
  settle_paper_trading        <- _gate_daily_price

Batch 3 (依赖 Batch 2):
  calc_extended_factor        <- _gate_daily_price + calc_basic_factor
  calc_factor_ic_monitor      <- 4个 factor 任务

Maintenance (手动触发, 不参与 daily DAG):
  update_industry_classify
  fetch_financial_statements
  validate_factors            <- 4个 factor 任务
  backfill_basic_factor
```

## 全部任务列表

| Task ID | Name | Module | Func | Tags |
|---------|------|--------|------|------|
| `fetch_macro_data` | Fetch macro indicators | `data_analyst.fetchers.macro_fetcher` | `fetch_all_indicators` | macro, daily |
| `calc_macro_factors` | Calculate macro factors | `data_analyst.factors.macro_factor_calculator` | `incremental_update` | macro, factor, daily |
| `_gate_daily_price` | Gate: wait for daily data | `scheduler.readiness` | `wait_for_daily_data` | gate, daily |
| `calc_basic_factor` | Calculate basic factors | `data_analyst.factors.basic_factor_calculator` | `calculate_and_save_factors` | factor, daily |
| `calc_extended_factor` | Calculate extended factors | `data_analyst.factors.extended_factor_calculator` | `main` | factor, daily |
| `calc_valuation_factor` | Calculate valuation factors | `data_analyst.factors.valuation_factor_calculator` | `main` | factor, daily |
| `calc_quality_factor` | Calculate quality factors | `data_analyst.factors.quality_factor_calculator` | `main` | factor, daily |
| `calc_technical_factor` | Calculate technical factors | `data_analyst.factors.factor_calculator` | `calculate_factors_for_date` | factor, daily |
| `calc_rps` | Calculate RPS | `data_analyst.indicators.rps_calculator` | `rps_daily_update` | indicator, daily |
| `calc_svd_monitor` | SVD market state monitor | `data_analyst.market_monitor.run_monitor` | `run_daily_monitor` | indicator, daily |
| `calc_log_bias` | Log bias signal detection | `scheduler.adapters` | `run_log_bias` | indicator, daily |
| `calc_technical_indicator` | Technical indicators | `scheduler.adapters` | `run_technical_indicator_scan` | indicator, daily |
| `calc_factor_ic_monitor` | Factor IC monitoring | `research.factor_monitor` | `run_monitor` | strategy, daily |
| `settle_paper_trading` | Settle paper trading | `scheduler.adapters` | `run_paper_trading_settle` | strategy, daily |
| `update_industry_classify` | Update industry classification | `scheduler.adapters` | `run_industry_update` | maintenance, manual |
| `fetch_financial_statements` | Fetch financial statements | `data_analyst.financial_fetcher.run_fetcher` | `main` | maintenance, manual |
| `validate_factors` | Validate factor effectiveness | `data_analyst.factors.factor_validator` | `main` | maintenance, manual |
| `backfill_basic_factor` | Backfill basic factors | `data_analyst.factors.backfill_factors` | `main` | maintenance, manual |

## 添加新任务

### 1. 在对应的 YAML 文件中添加任务定义

例如在 `tasks/04_indicators.yaml` 中新增：

```yaml
  - id: calc_my_indicator
    name: "My custom indicator"
    module: data_analyst.indicators.my_indicator
    func: calculate
    tags: [indicator, daily]
    schedule: "after_gate"
    depends_on:
      - _gate_daily_price
    params:
      window: 20
    retry:
      max_attempts: 3
      delay_seconds: 60
    timeout_seconds: 600
    alert_on_failure: true
```

### 2. 任务字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 任务唯一标识，用于 CLI 和依赖声明 |
| `name` | 否 | 人类可读名称 |
| `module` | 是 | Python 模块路径 |
| `func` | 是 | 模块中的函数名，会被 `**params` 调用 |
| `tags` | 否 | 标签列表，用于 `--tag` 过滤 |
| `schedule` | 否 | 调度时间标记（`"17:30"`, `"after_gate"`, `"manual"`），当前仅作文档用途 |
| `depends_on` | 否 | 依赖的任务 ID 列表 |
| `params` | 否 | 传递给函数的关键字参数 |
| `enabled` | 否 | 是否启用，默认 true |
| `dry_run` | 否 | 是否以 dry-run 模式运行，默认 false |
| `retry.max_attempts` | 否 | 最大重试次数，默认 2 |
| `retry.delay_seconds` | 否 | 重试间隔秒数，默认 30 |
| `timeout_seconds` | 否 | 超时秒数，默认 1800 |
| `alert_on_failure` | 否 | 失败时是否发送 webhook 通知，默认 false |
| `env.<env>.enabled` | 否 | 特定环境下是否启用 |

### 3. 三层配置合并

配置按以下优先级合并（后者覆盖前者）：

1. `_base.yaml` 中的 `defaults`
2. 任务 YAML 中的字段
3. `env.<MYTRADER_ENV>` 中的环境覆盖

环境由 `MYTRADER_ENV` 环境变量控制，默认 `local`。

### 4. 函数要求

被调度的函数需满足以下条件之一：

- **零参数函数**: `def main(): ...` -- 直接调用
- **带参数函数**: `def calculate(window=20): ...` -- params 中的键值作为 kwargs 传入
- **支持 dry_run**: `def run(dry_run=False): ...` -- dry-run 时自动传入 `dry_run=True`

如果模块没有合适的入口函数，在 `scheduler/adapters.py` 中添加一个适配器包装。

## Readiness Gate

`_gate_daily_price` 任务通过轮询数据库替代固定时间调度：

1. 计算预期交易日（工作日当天，周末回退到周五）
2. 查询 `trade_stock_daily` 表的 `MAX(trade_date)`
3. 如果匹配则通过，否则每 5 分钟重试
4. 超时（默认 60 分钟）抛出 `TimeoutError`

dry-run 模式下只检查一次，不轮询。

## 报警通知

任务失败时可通过飞书/Lark Webhook 发送通知。

### 配置

在 `.env` 中设置（二选一）：

```bash
# 优先使用
ALERT_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 回退到
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

### 触发条件

- 任务设置 `alert_on_failure: true`
- 所有重试耗尽后仍失败

通知内容包含：任务名、模块路径、错误信息、重试次数、耗时。

## 状态持久化

每次任务执行都会记录到数据库 `task_runs` 表。

### 表结构

```sql
CREATE TABLE IF NOT EXISTS task_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(100) NOT NULL,
    env VARCHAR(20) NOT NULL DEFAULT 'local',
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    duration_s DOUBLE DEFAULT 0,
    error_msg TEXT NULL,
    retry_count INT DEFAULT 0,
    triggered_by VARCHAR(50) DEFAULT 'cli',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_task_id (task_id),
    INDEX idx_status (status),
    INDEX idx_started_at (started_at)
);
```

首次运行 `python -m scheduler run ...` 时自动建表。

## 模块结构

```
scheduler/
  __init__.py          # 包声明
  __main__.py          # python -m scheduler 入口
  cli.py               # CLI 子命令 (list/run/status/summary)
  loader.py            # YAML 加载 + 三层环境合并
  dag.py               # 拓扑排序 + 批次执行 + 子图提取
  executor.py          # 任务执行 (import + 调用 + 重试 + 超时)
  state.py             # task_runs 表 DDL + 读写
  readiness.py         # 数据就绪探测 (轮询 DB)
  alert.py             # Webhook 通知
  adapters.py          # 模块适配器 (无简单入口的包装函数)
  tests/
    test_init.py
    test_cli.py
    test_loader.py
    test_dag.py
    test_executor.py
    test_state.py
    test_readiness.py
    test_alert.py
    test_adapters.py
    test_integration.py

tasks/
  _base.yaml           # 全局默认值 + 环境配置
  02_macro.yaml        # 宏观数据
  03_factors_basic.yaml # 因子计算 + gate
  04_indicators.yaml   # 技术指标
  05_strategy.yaml     # 策略相关
  06_maintenance.yaml  # 维护任务
```

## 运行测试

```bash
# 全部测试（不需要数据库）
pytest scheduler/tests/ -v

# 单个模块测试
pytest scheduler/tests/test_dag.py -v
pytest scheduler/tests/test_executor.py -v
pytest scheduler/tests/test_integration.py -v
```

## 常见问题

### Q: 如何跳过 gate 直接执行因子计算？

```bash
# 直接运行目标任务，dry-run 只打印不执行
python -m scheduler run calc_basic_factor --dry-run
```

`run` 命令会自动拉取依赖链。如果不想要 gate，可以在 YAML 中临时移除 `depends_on` 中的 `_gate_daily_price`，或用 `--dry-run` 跳过实际执行。

### Q: 如何在 cron 中使用？

```bash
# crontab 示例：每天 18:00 运行全部 daily 任务
0 18 * * 1-5 cd /path/to/myTrader && python -m scheduler run all --tag daily >> /path/to/scheduler.log 2>&1
```

### Q: manual 任务在 prod 环境下会被跳过吗？

是的。`schedule: manual` 的任务在 `env=prod` 且非 dry-run 时会被自动跳过。手动任务始终通过显式命令执行：

```bash
python -m scheduler run validate_factors --env local
```

### Q: 如何添加适配器？

如果目标模块没有简单的零参数入口函数，在 `scheduler/adapters.py` 中添加包装：

```python
def run_my_task(dry_run: bool = False):
    if dry_run:
        logger.info("[DRY-RUN] run_my_task")
        return
    from some.module import SomeClass
    SomeClass().run()
```

然后在 YAML 中引用 `scheduler.adapters:run_my_task`。
