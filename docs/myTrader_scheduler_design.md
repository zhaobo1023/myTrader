# myTrader 任务调度系统技术方案

> 版本：v1.0 · 2026-04-04  
> 适用环境：Windows (QMT) · Mac/本地开发 · 阿里云 ECS

---

## 一、现状分析与问题定位

### 1.1 当前架构

```
Windows Server (QMT)
  └── 每日盘后拉取行情/财务数据
  └── 双写 → 本地DB (192.168.97.1) + 阿里云DB (123.56.3.1)

Mac 本地
  └── daily_run.py (step1/2/3 顺序执行)
  └── scheduler_service.py (18:00 / 18:30 定时)
  └── scripts/ 各种脚本手动调用
  └── 计算因子/指标 → 双写两端DB
```

### 1.2 核心问题

| 问题 | 根因 |
|------|------|
| 任务没按预期执行 | Windows→Mac 无就绪信号，Mac 侧任务开始时数据可能未就绪 |
| 失败完全不知道 | 无执行状态持久化，无失败通知机制 |
| 任务散落三处 | `daily_run.py` + `scheduler_service.py` + 手动脚本，无统一入口 |
| 多环境区分弱 | `.env` 只区分DB连接，任务的启停/dry_run/频率没有按环境结构化配置 |
| 2个表未纳入管理 | `trade_technical_indicator`、`pt_rounds/pt_positions` 游离在外 |

### 1.3 最关键的隐患：跨机器依赖无信号

Mac 端所有因子计算依赖 `trade_stock_daily` 就绪，但目前没有任何机制检测 Windows 端是否写完。`scheduler_service.py` 用 18:00 固定时间做"数据完整性检查"，本质是在赌 Windows 端一定在 18:00 前写完，节假日、QMT 故障、网络抖动都会打破这个假设。

---

## 二、整体设计

### 2.1 架构全景

```
┌─────────────────────────────────────────────────────┐
│  Task Registry  (tasks/*.yaml)                      │
│  统一声明：任务定义 / 依赖 / 调度规则 / 环境开关        │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Readiness Gate                                     │
│  轮询 trade_stock_daily 最新日期，就绪后才放行 Mac 任务  │
└──────────┬────────────────────────────┬─────────────┘
           │                            │
┌──────────▼──────────┐   ┌────────────▼────────────┐
│  DAG Runner (Mac)   │   │  Windows Scheduler      │
│  拓扑排序执行因子链  │   │  QMT任务 + 双写          │
└──────────┬──────────┘   └─────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────┐
│  Task Executor                                      │
│  重试 / 超时 / dry_run / 异常捕获                    │
└──────────┬──────────────────────────────────────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼───┐   ┌────▼────┐
│ State │   │  Alert  │
│ MySQL │   │ 微信推送 │
└───────┘   └─────────┘
```

### 2.2 三大新增机制

**机制1：Readiness Gate（跨机器依赖的核心解法）**

不再依赖固定时间，改为主动探测数据就绪：

```python
# scheduler/readiness.py
def wait_for_daily_data(target_date: str, timeout_min: int = 60) -> bool:
    """
    轮询检查 trade_stock_daily 是否已包含 target_date 的数据
    每 5 分钟检查一次，超时后告警
    """
```

**机制2：统一 YAML 任务注册**

所有任务（含原来手动跑的脚本）都在 `tasks/` 下声明，不再有游离的调用入口。

**机制3：task_runs 执行记录表**

每次任务执行写一条记录，失败立即 Webhook 推送，告别"只看结果异常"。

---

## 三、目录结构

```
mytrader/
│
├── scheduler/                    # 新增：调度框架核心
│   ├── __init__.py
│   ├── cli.py                    # 统一入口：python -m scheduler
│   ├── loader.py                 # YAML 解析 + 环境 merge
│   ├── dag.py                    # 依赖 DAG 解析 + 拓扑排序
│   ├── executor.py               # 单任务执行、重试、超时、dry_run
│   ├── readiness.py              # 跨机器数据就绪探测
│   ├── state.py                  # task_runs 表读写
│   └── alert.py                  # 微信/钉钉 Webhook 通知
│
├── tasks/                        # 新增：任务定义（全量）
│   ├── _base.yaml                # 公共默认值
│   ├── 01_data_fetch.yaml        # Windows 端数据拉取（监控用，不执行）
│   ├── 02_macro.yaml             # 宏观数据拉取 + 因子计算
│   ├── 03_factors_basic.yaml     # 基础/扩展/估值/质量/技术因子
│   ├── 04_indicators.yaml        # RPS / SVD / LogBias / 技术指标
│   ├── 05_strategy.yaml          # 模拟交易信号 / 板块轮动
│   └── 06_maintenance.yaml       # 因子验证 / 行业分类 / 财务数据（手动）
│
├── daily_run.py                  # 保留 → 最终改为一行调用后废弃
├── data_analyst/
├── strategist/
├── research/
└── scripts/                      # 逐步迁移，迁完后废弃
```

---

## 四、YAML 任务定义

### 4.1 基础配置 `tasks/_base.yaml`

```yaml
defaults:
  retry:
    max_attempts: 3
    delay_seconds: 60
  timeout_seconds: 600
  alert_on_failure: false
  dry_run: false
  enabled: true

environments:
  local:
    alert_on_failure: false
    dry_run: true              # 本地默认不写库，只验证逻辑
    data_source: cache         # 本地优先用缓存数据
  prod:
    alert_on_failure: true
    dry_run: false
    data_source: live
```

### 4.2 宏观任务 `tasks/02_macro.yaml`

```yaml
tasks:
  - id: fetch_macro_data
    name: "宏观数据拉取"
    module: data_analyst.fetchers.macro_fetcher
    func: run
    tags: [macro, daily]
    schedule:
      local: manual
      prod: "17:30"             # 不依赖 trade_stock_daily，可以先跑
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }
    alert_on_failure: true

  - id: calc_macro_factors
    name: "宏观因子计算"
    module: data_analyst.factors.macro_factor_calculator
    func: run
    tags: [macro, factor, daily]
    depends_on:
      - fetch_macro_data
    schedule:
      local: manual
      prod: "17:35"
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }
```

### 4.3 核心因子任务 `tasks/03_factors_basic.yaml`

```yaml
# 所有因子任务的共同前置：等待 Windows 端行情数据就绪
# 通过 readiness_gate: trade_stock_daily 触发，而非固定时间

tasks:
  - id: _gate_daily_price           # 虚拟任务，代表数据就绪事件
    name: "日线行情就绪检测"
    module: scheduler.readiness
    func: wait_for_daily_data
    tags: [gate]
    schedule:
      local: manual
      prod: "17:45"                 # 从这个时间开始轮询，最多等60分钟
    params:
      timeout_min: 60
    env:
      local: { enabled: false }     # 本地不等，直接用已有数据
      prod:  { enabled: true }
    alert_on_failure: true          # 超时未就绪立即告警

  - id: calc_basic_factor
    name: "基础因子计算"
    module: data_analyst.factors.basic_factor_calculator
    func: run
    tags: [factor, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate              # gate 就绪后立即触发
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }
    retry:
      max_attempts: 2
      delay_seconds: 120

  - id: calc_extended_factor
    name: "扩展因子计算"
    module: data_analyst.factors.extended_factor_calculator
    func: run
    tags: [factor, daily]
    depends_on:
      - _gate_daily_price
      - calc_basic_factor           # 部分扩展因子引用基础因子
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }

  - id: calc_valuation_factor
    name: "估值因子计算"
    module: data_analyst.factors.valuation_factor_calculator
    func: run
    tags: [factor, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }

  - id: calc_quality_factor
    name: "质量因子计算"
    module: data_analyst.factors.quality_factor_calculator
    func: run
    tags: [factor, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }

  - id: calc_technical_factor
    name: "技术因子计算 (TA-Lib)"
    module: data_analyst.factors.factor_calculator
    func: run
    tags: [factor, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }
```

### 4.4 指标任务 `tasks/04_indicators.yaml`

```yaml
tasks:
  - id: calc_rps
    name: "RPS 增量更新"
    module: data_analyst.indicators.rps_calculator
    func: run
    tags: [indicator, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    params:
      mode: latest
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }

  - id: calc_svd_monitor
    name: "SVD 市场状态监控"
    module: data_analyst.market_monitor.run_monitor
    func: run
    tags: [indicator, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    params:
      mode: latest
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }

  - id: calc_log_bias
    name: "Log Bias 计算"
    module: strategist.log_bias.calculator
    func: run
    tags: [indicator, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }

  - id: calc_technical_indicator
    name: "技术指标扫描"             # 原来未改造，现纳入统一管理
    module: data_analyst.indicators.technical
    func: run
    tags: [indicator, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: false }       # 本地数据量大，默认关
      prod:  { enabled: true, dry_run: false }
```

### 4.5 策略任务 `tasks/05_strategy.yaml`

```yaml
tasks:
  - id: calc_factor_ic_monitor
    name: "因子滚动 IC 监控"
    module: research.factor_monitor
    func: run
    tags: [strategy, daily]
    depends_on:
      - calc_basic_factor
      - calc_extended_factor
      - calc_valuation_factor
      - calc_quality_factor
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }
    alert_on_failure: true

  - id: gen_paper_trading_signal
    name: "模拟交易信号生成"          # 原来未纳入统一管理
    module: strategist.xgboost_strategy.paper_trading.signal
    func: run
    tags: [strategy, weekly]
    depends_on:
      - calc_basic_factor
      - calc_extended_factor
      - calc_technical_factor
    schedule:
      local: manual
      prod: "fri 17:30"
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }
    alert_on_failure: true

  - id: settle_paper_trading
    name: "模拟持仓每日结算"
    module: strategist.xgboost_strategy.paper_trading.settler
    func: run
    tags: [strategy, daily]
    depends_on:
      - _gate_daily_price
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: false }       # 本地不结算
      prod:  { enabled: true, dry_run: false }

  - id: update_sector_rotation
    name: "板块轮动评分"
    module: research.sector_rotation
    func: run
    tags: [strategy, daily]
    depends_on:
      - calc_basic_factor
      - calc_rps
    schedule:
      local: manual
      prod: after_gate
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }

### 4.6 维护任务 `tasks/06_maintenance.yaml`

```yaml
tasks:
  - id: update_industry_classify
    name: "行业分类更新"
    module: strategist.multi_factor.industry_fetcher
    func: run
    tags: [maintenance, weekly]
    schedule:
      local: manual
      prod:  manual                   # 始终手动，不自动触发
    env:
      local: { enabled: true, dry_run: false }
      prod:  { enabled: true, dry_run: false }

  - id: fetch_financial_statements
    name: "财务报表拉取（季度）"
    module: data_analyst.financial_fetcher.runner
    func: run
    tags: [maintenance, quarterly]
    schedule:
      local: manual
      prod:  manual
    env:
      local: { enabled: false }
      prod:  { enabled: true, dry_run: false }
    alert_on_failure: true

  - id: validate_factors
    name: "因子有效性验证"
    module: data_analyst.factors.factor_validator
    func: run
    tags: [maintenance]
    schedule:
      local: manual
      prod:  manual
    env:
      local: { enabled: true, dry_run: false }
      prod:  { enabled: true, dry_run: false }

  - id: backfill_basic_factor
    name: "基础因子历史回填"
    module: data_analyst.factors.backfill_factors
    func: run
    tags: [maintenance, backfill]
    schedule:
      local: manual
      prod:  manual
    env:
      local: { enabled: true, dry_run: true }
      prod:  { enabled: true, dry_run: false }
```

---

## 五、核心代码实现

### 5.1 数据就绪探测 `scheduler/readiness.py`

```python
import time
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from config import get_db_engine

logger = logging.getLogger(__name__)

def get_latest_trade_date() -> str:
    """从数据库获取 trade_stock_daily 最新交易日期"""
    engine = get_db_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT MAX(trade_date) as latest FROM trade_stock_daily"
        )).fetchone()
        return str(row["latest"]) if row and row["latest"] else ""

def expected_trade_date() -> str:
    """
    判断今天应该有的最新交易日：
    - 如果今天是交易日且已过15:30，期望日期 = 今天
    - 否则期望日期 = 上一个交易日
    注意：简化实现，完整版需对接交易日历
    """
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:  # 周末
        days_back = weekday - 4
        return (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
    if now.hour < 16:  # 未收盘
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")

def run(dry_run: bool = False, timeout_min: int = 60, **kwargs) -> bool:
    """
    Readiness Gate 任务入口。
    轮询直到 trade_stock_daily 包含期望交易日数据，或超时告警。
    """
    expected = expected_trade_date()
    deadline = time.time() + timeout_min * 60
    interval = 300  # 每5分钟检查一次

    logger.info(f"[readiness] 等待 trade_stock_daily 就绪，期望日期: {expected}")

    while time.time() < deadline:
        latest = get_latest_trade_date()
        if latest >= expected:
            logger.info(f"[readiness] 数据就绪: {latest}")
            return True
        remaining = int((deadline - time.time()) / 60)
        logger.info(f"[readiness] 当前最新: {latest}，期望: {expected}，剩余等待: {remaining}min")
        time.sleep(interval)

    raise TimeoutError(
        f"trade_stock_daily 超时未就绪。期望: {expected}，当前最新: {get_latest_trade_date()}"
    )
```

### 5.2 YAML 加载与环境合并 `scheduler/loader.py`

```python
import yaml, os
from pathlib import Path

ENV = os.getenv("MYTRADER_ENV", "local")  # local | prod

def load_tasks(tasks_dir: str = "tasks") -> list[dict]:
    base_defaults = _load_base_defaults(tasks_dir)
    tasks = []
    for f in sorted(Path(tasks_dir).glob("[0-9]*.yaml")):
        with open(f) as fp:
            data = yaml.safe_load(fp)
        for task in data.get("tasks", []):
            merged = _merge_task(base_defaults, task, ENV)
            tasks.append(merged)
    return tasks

def _load_base_defaults(tasks_dir: str) -> dict:
    base_file = Path(tasks_dir) / "_base.yaml"
    if not base_file.exists():
        return {}
    with open(base_file) as fp:
        base = yaml.safe_load(fp)
    defaults = base.get("defaults", {})
    env_defaults = base.get("environments", {}).get(ENV, {})
    return {**defaults, **env_defaults}

def _merge_task(base_defaults: dict, task: dict, env: str) -> dict:
    result = {**base_defaults}
    # task 级别覆盖（排除 env/schedule 嵌套字段）
    for k, v in task.items():
        if k not in ("env", "schedule"):
            result[k] = v
    # env-specific 覆盖
    env_overrides = task.get("env", {}).get(env, {})
    result.update(env_overrides)
    # 调度表达式
    result["schedule_expr"] = task.get("schedule", {}).get(env, "manual")
    result["_env"] = env
    return result
```

### 5.3 DAG 执行器 `scheduler/dag.py`

```python
from graphlib import TopologicalSorter, CycleError
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)

def resolve_batches(tasks: list[dict]) -> list[list[dict]]:
    """将任务列表按依赖关系分解为可并行的执行批次"""
    task_map = {t["id"]: t for t in tasks}
    graph = {}
    for t in tasks:
        deps = t.get("depends_on", [])
        # 过滤掉当前批次中不存在的依赖（跨文件依赖）
        graph[t["id"]] = {d for d in deps if d in task_map}

    try:
        sorter = TopologicalSorter(graph)
        sorter.prepare()
    except CycleError as e:
        raise ValueError(f"任务依赖存在循环: {e}")

    batches = []
    while sorter.is_active():
        ready_ids = list(sorter.get_ready())
        batches.append([task_map[tid] for tid in ready_ids])
        for tid in ready_ids:
            sorter.done(tid)
    return batches

def run_dag(tasks: list[dict], executor_fn, max_workers: int = 4) -> dict[str, str]:
    """
    按 DAG 顺序执行任务。同一批次内并行，批次间串行。
    返回 {task_id: status} 字典。
    """
    batches = resolve_batches(tasks)
    completed = {}

    for i, batch in enumerate(batches):
        logger.info(f"── 批次 {i+1}/{len(batches)}: {[t['id'] for t in batch]}")

        if len(batch) == 1:
            task = batch[0]
            status = executor_fn(task, completed)
            completed[task["id"]] = status
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(batch))) as pool:
                futures = {pool.submit(executor_fn, t, completed): t for t in batch}
                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        status = future.result()
                    except Exception as e:
                        status = "failed"
                        logger.error(f"[{task['id']}] 并行执行异常: {e}")
                    completed[task["id"]] = status

    return completed
```

### 5.4 任务执行器 `scheduler/executor.py`

```python
import importlib, time, traceback, logging
from datetime import datetime
from .state import TaskRun, save_run
from .alert import send_alert

logger = logging.getLogger(__name__)

def execute_task(task: dict, completed: dict[str, str]) -> str:
    """
    执行单个任务，处理：依赖检查、enabled检查、dry_run、重试、超时、状态记录、告警
    """
    tid = task["id"]

    # 1. 检查上游依赖
    for dep in task.get("depends_on", []):
        dep_status = completed.get(dep)
        if dep_status and dep_status != "success":
            logger.warning(f"[{tid}] SKIPPED — 上游 '{dep}' 状态: {dep_status}")
            _record_and_return(task, "skipped", error_msg=f"上游 {dep} 未成功")
            return "skipped"

    # 2. 检查是否启用
    if not task.get("enabled", True):
        logger.info(f"[{tid}] 当前环境已禁用，跳过")
        return "skipped"

    # 3. 检查手动任务（prod 环境不自动跑 manual 任务）
    if task.get("schedule_expr") == "manual" and task.get("_env") == "prod":
        logger.info(f"[{tid}] manual 任务，跳过自动调度")
        return "skipped"

    # 4. 执行（含重试）
    retry_cfg = task.get("retry", {})
    max_attempts = retry_cfg.get("max_attempts", 1)
    delay_s = retry_cfg.get("delay_seconds", 60)
    timeout_s = task.get("timeout_seconds", 600)
    dry_run = task.get("dry_run", False)

    run = TaskRun(
        task_id=tid,
        env=task["_env"],
        started_at=datetime.now(),
        triggered_by="scheduler"
    )
    status = "failed"
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        try:
            mod = importlib.import_module(task["module"])
            func = getattr(mod, task["func"])
            params = task.get("params", {})

            t0 = time.time()
            if dry_run:
                logger.info(f"[{tid}] DRY RUN（不写库）")
                func(dry_run=True, **params)
            else:
                func(**params)

            run.duration_s = time.time() - t0
            run.retry_count = attempt - 1
            status = "success"
            logger.info(f"[{tid}] 成功，耗时 {run.duration_s:.1f}s")
            break

        except Exception:
            last_error = traceback.format_exc()
            run.error_msg = last_error
            logger.error(f"[{tid}] 第 {attempt}/{max_attempts} 次失败:\n{last_error[-500:]}")
            if attempt < max_attempts:
                logger.info(f"[{tid}] {delay_s}s 后重试...")
                time.sleep(delay_s)

    run.status = status
    run.finished_at = datetime.now()
    save_run(run)

    if status == "failed" and task.get("alert_on_failure", False):
        send_alert(task, run, completed)

    return status

def _record_and_return(task, status, error_msg=""):
    run = TaskRun(
        task_id=task["id"], env=task["_env"],
        started_at=datetime.now(), finished_at=datetime.now(),
        status=status, error_msg=error_msg
    )
    save_run(run)
```

### 5.5 执行状态表 `scheduler/state.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from sqlalchemy import text
from config import get_db_engine

# DDL：首次运行时执行一次
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_runs (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id       VARCHAR(64)  NOT NULL,
  env           VARCHAR(16)  NOT NULL,
  status        VARCHAR(16)  NOT NULL,
  started_at    DATETIME,
  finished_at   DATETIME,
  duration_s    FLOAT,
  error_msg     TEXT,
  retry_count   TINYINT DEFAULT 0,
  triggered_by  VARCHAR(32)  DEFAULT 'scheduler',
  INDEX idx_task_date (task_id, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

@dataclass
class TaskRun:
    task_id: str
    env: str
    started_at: datetime
    status: str = "running"
    finished_at: Optional[datetime] = None
    duration_s: Optional[float] = None
    error_msg: Optional[str] = None
    retry_count: int = 0
    triggered_by: str = "scheduler"

def save_run(run: TaskRun):
    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO task_runs
              (task_id, env, status, started_at, finished_at,
               duration_s, error_msg, retry_count, triggered_by)
            VALUES
              (:task_id, :env, :status, :started_at, :finished_at,
               :duration_s, :error_msg, :retry_count, :triggered_by)
        """), run.__dict__)
        conn.commit()

def recent_runs(task_id: str, n: int = 10) -> list[dict]:
    engine = get_db_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT task_id, env, status, started_at, finished_at,
                   duration_s, retry_count, error_msg
            FROM task_runs
            WHERE task_id = :tid
            ORDER BY started_at DESC LIMIT :n
        """), {"tid": task_id, "n": n})
        return [dict(r._mapping) for r in rows]

def today_summary(env: str = "prod") -> list[dict]:
    """查今日所有任务执行概况，用于日报"""
    engine = get_db_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT task_id, status, duration_s, started_at, retry_count
            FROM task_runs
            WHERE env = :env AND DATE(started_at) = CURDATE()
            ORDER BY started_at
        """), {"env": env})
        return [dict(r._mapping) for r in rows]
```

### 5.6 告警通知 `scheduler/alert.py`

```python
import requests, os, logging
from .state import TaskRun

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")  # 企业微信/钉钉 Webhook

def send_alert(task: dict, run: TaskRun, completed: dict):
    if not WEBHOOK_URL:
        logger.debug("未配置 ALERT_WEBHOOK_URL，跳过告警")
        return

    # 上游状态摘要
    deps = task.get("depends_on", [])
    if deps:
        upstream = "\n".join(
            f"  {'✓' if completed.get(d) == 'success' else '✗'} {d}: {completed.get(d, '未执行')}"
            for d in deps
        )
    else:
        upstream = "  无上游依赖"

    error_brief = (run.error_msg or "")[-300:].strip()

    content = f"""[myTrader] 任务执行失败
────────────────────────
任务: {task.get('name', task['id'])}
ID:   {task['id']}
环境: {run.env}
时间: {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}
耗时: {run.duration_s or 0:.1f}s  重试次数: {run.retry_count}

上游依赖状态:
{upstream}

错误信息:
{error_brief}"""

    try:
        # 兼容企业微信和钉钉格式
        requests.post(
            WEBHOOK_URL,
            json={"msgtype": "text", "text": {"content": content}},
            timeout=10
        )
    except Exception as e:
        logger.error(f"告警发送失败: {e}")

def send_daily_summary(summary: list[dict], env: str):
    """发送每日任务执行日报"""
    if not WEBHOOK_URL:
        return

    success = sum(1 for r in summary if r["status"] == "success")
    failed  = sum(1 for r in summary if r["status"] == "failed")
    skipped = sum(1 for r in summary if r["status"] == "skipped")

    lines = [f"  {'✓' if r['status']=='success' else '✗'} {r['task_id']} "
             f"({r['duration_s'] or 0:.0f}s)"
             for r in summary]

    content = f"""[myTrader] 每日任务执行日报 ({env})
────────────────────────
成功: {success}  失败: {failed}  跳过: {skipped}

{chr(10).join(lines)}"""

    try:
        requests.post(
            WEBHOOK_URL,
            json={"msgtype": "text", "text": {"content": content}},
            timeout=10
        )
    except Exception as e:
        logger.error(f"日报发送失败: {e}")
```

### 5.7 统一 CLI 入口 `scheduler/cli.py`

```python
import argparse, logging, os
from .loader import load_tasks, ENV
from .dag import run_dag, resolve_batches
from .executor import execute_task
from .state import recent_runs, today_summary
from .alert import send_daily_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

def cmd_list(args):
    tasks = load_tasks()
    if args.tag:
        tags = args.tag.split(",")
        tasks = [t for t in tasks if any(tag in t.get("tags", []) for tag in tags)]

    env = os.getenv("MYTRADER_ENV", "local")
    print(f"\n当前环境: {env}  共 {len(tasks)} 个任务\n")
    print(f"{'ID':<40} {'名称':<22} {'调度':<15} {'enabled':<8} {'dry_run'}")
    print("─" * 100)
    for t in tasks:
        print(f"{t['id']:<40} {t.get('name',''):<22} "
              f"{t.get('schedule_expr','manual'):<15} "
              f"{str(t.get('enabled', True)):<8} "
              f"{t.get('dry_run', False)}")

def cmd_run(args):
    tasks = load_tasks()

    # 按 tag 或 task_id 过滤
    if args.task != "all":
        if args.tag:
            tags = args.tag.split(",")
            tasks = [t for t in tasks if any(tag in t.get("tags", []) for tag in tags)]
        else:
            tasks = [t for t in tasks if t["id"] == args.task]
            if not tasks:
                print(f"未找到任务: {args.task}")
                return

    if args.dry_run:  # 命令行强制 dry_run 覆盖
        for t in tasks:
            t["dry_run"] = True

    print(f"\n准备执行 {len(tasks)} 个任务...\n")
    completed = run_dag(tasks, execute_task)

    # 打印摘要
    print("\n── 执行摘要 ──────────────────────────────")
    for tid, status in completed.items():
        marker = "✓" if status == "success" else ("↷" if status == "skipped" else "✗")
        print(f"  {marker} {tid}: {status}")

def cmd_status(args):
    runs = recent_runs(args.task, args.n)
    if not runs:
        print(f"无执行记录: {args.task}")
        return
    print(f"\n最近 {len(runs)} 次执行 | {args.task}\n")
    print(f"{'时间':<22} {'环境':<8} {'状态':<10} {'耗时':>8}  {'重试'}")
    print("─" * 60)
    for r in runs:
        print(f"{str(r['started_at']):<22} {r['env']:<8} {r['status']:<10} "
              f"{r['duration_s'] or 0:>7.1f}s  {r['retry_count']}")

def cmd_summary(args):
    env = os.getenv("MYTRADER_ENV", "prod")
    summary = today_summary(env)
    print(f"\n今日任务执行概况 ({env})\n")
    for r in summary:
        marker = "✓" if r["status"] == "success" else "✗"
        print(f"  {marker} {r['task_id']:<40} {r['status']:<10} {r['duration_s'] or 0:.0f}s")
    if args.notify:
        send_daily_summary(summary, env)
        print("\n已发送日报通知")

def main():
    parser = argparse.ArgumentParser(
        prog="python -m scheduler",
        description="myTrader 任务调度系统"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # list
    p_list = sub.add_parser("list", help="列出任务")
    p_list.add_argument("--tag", help="按标签过滤，逗号分隔")

    # run
    p_run = sub.add_parser("run", help="执行任务")
    p_run.add_argument("task", help="task_id 或 'all'")
    p_run.add_argument("--tag", help="按标签批量执行")
    p_run.add_argument("--dry-run", action="store_true", help="强制 dry_run 模式")

    # status
    p_status = sub.add_parser("status", help="查看执行历史")
    p_status.add_argument("task", help="task_id")
    p_status.add_argument("--n", type=int, default=10)

    # summary
    p_summary = sub.add_parser("summary", help="今日执行概况")
    p_summary.add_argument("--notify", action="store_true", help="同时发送 Webhook 通知")

    args = parser.parse_args()
    {
        "list":    cmd_list,
        "run":     cmd_run,
        "status":  cmd_status,
        "summary": cmd_summary,
    }[args.cmd](args)

if __name__ == "__main__":
    main()
```

---

## 六、常用命令速查

```bash
# ─── 本地开发 ───────────────────────────────────────────────────

# 查看所有任务（本地环境）
MYTRADER_ENV=local python -m scheduler list

# 只跑策略逻辑，用已有缓存数据（不重算依赖）
MYTRADER_ENV=local python -m scheduler run gen_paper_trading_signal

# 跑完整日频链路（自动按依赖顺序）
MYTRADER_ENV=local python -m scheduler run all --tag daily

# 验证新因子逻辑，强制 dry_run（不写库）
MYTRADER_ENV=local python -m scheduler run calc_basic_factor --dry-run

# 查某任务最近执行历史
python -m scheduler status calc_multifactor --n 20

# 查今日所有任务执行情况
MYTRADER_ENV=prod python -m scheduler summary

# ─── 生产服务器（crontab 配置）───────────────────────────────────

# 每日 17:30 启动（Readiness Gate 会自行等待数据就绪）
30 17 * * 1-5 cd /path/to/mytrader && MYTRADER_ENV=prod python -m scheduler run all --tag daily

# 每周五 17:30 额外跑周频任务
30 17 * * 5   cd /path/to/mytrader && MYTRADER_ENV=prod python -m scheduler run all --tag weekly

# 每日 22:00 发送日报
0 22 * * 1-5  cd /path/to/mytrader && MYTRADER_ENV=prod python -m scheduler summary --notify

# 每季度财报发布后手动执行
MYTRADER_ENV=prod python -m scheduler run fetch_financial_statements
```

---

## 七、完整任务依赖图

```
每日自动执行链路（prod 环境，交易日）

17:30  fetch_macro_data
  └──▶ calc_macro_factors

17:45  _gate_daily_price ← 轮询 trade_stock_daily 就绪（最多等60分钟）
  │
  ├──▶ calc_basic_factor          ─┐
  ├──▶ calc_valuation_factor       │  并行执行
  ├──▶ calc_quality_factor         │
  ├──▶ calc_rps                    │
  ├──▶ calc_svd_monitor            │
  ├──▶ calc_log_bias               │
  └──▶ calc_technical_indicator   ─┘
        │
        ▼
  calc_extended_factor（依赖 basic_factor）
        │
        ▼
  calc_technical_factor（依赖 daily_price）
        │
        ├──▶ calc_factor_ic_monitor（依赖所有因子）
        ├──▶ settle_paper_trading
        └──▶ update_sector_rotation（依赖 basic + rps）

每周五额外执行：
  gen_paper_trading_signal（依赖 basic + extended + technical factor）

手动执行（不进自动调度）：
  update_industry_classify
  fetch_financial_statements
  validate_factors
  backfill_basic_factor
```

---

## 八、迁移路径（4步，不停服）

### 第1步（1天）：基础设施落地

```bash
# 1. 建 task_runs 表（两端数据库都执行）
CREATE TABLE IF NOT EXISTS task_runs ( ... );  # 见 state.py 中 DDL

# 2. 安装依赖
pip install pyyaml sqlalchemy

# 3. 创建 scheduler/ 和 tasks/ 目录，复制代码骨架
# 4. 配置 .env 新增两个变量
MYTRADER_ENV=local
ALERT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
```

### 第2步（2天）：迁移宏观 + 数据检测任务

将 `daily_run.py` 中 step1/step2（宏观数据）迁移进 `tasks/02_macro.yaml`，验证：

```bash
MYTRADER_ENV=local python -m scheduler run all --tag macro
```

### 第3步（3天）：迁移所有因子任务

重点是把 `depends_on` 依赖关系梳理正确，跑完整链路确认顺序：

```bash
MYTRADER_ENV=local python -m scheduler run all --tag daily --dry-run
# 确认依赖顺序打印正确后，去掉 --dry-run 跑真实计算
```

### 第4步（1天）：上生产 + 废弃旧入口

```python
# daily_run.py 最终形态（保留1个月后删除）
import subprocess, sys
result = subprocess.run(
    ["python", "-m", "scheduler", "run", "all", "--tag", "daily"],
    env={**os.environ, "MYTRADER_ENV": "prod"}
)
sys.exit(result.returncode)
```

配置 crontab，停掉 `scheduler_service.py`（它的18:00/18:30功能已被 Readiness Gate 取代）。

---

## 九、数据库表清单与管理归属

| 表名 | 写入端 | 双写 | 纳入调度 | 备注 |
|------|--------|------|----------|------|
| trade_stock_daily | Windows/QMT | 独立双写 | Gate监控 | 所有因子的上游依赖 |
| trade_etf_daily | Windows/QMT | 独立双写 | 否 | |
| trade_hk_daily | Windows/QMT | 独立双写 | 否 | |
| trade_stock_financial | Windows/QMT | 独立双写 | 否 | |
| trade_stock_daily_basic | Windows+Mac | 是 | 是 | akshare |
| macro_data | Mac | 是 | 是 | fetch_macro_data |
| macro_factors | Mac | 是 | 是 | calc_macro_factors |
| trade_stock_rps | Mac | 是 | 是 | calc_rps |
| trade_svd_market_state | Mac | 是 | 是 | calc_svd_monitor |
| trade_stock_basic_factor | Mac | 是 | 是 | calc_basic_factor |
| trade_stock_extended_factor | Mac | 是 | 是 | calc_extended_factor |
| trade_stock_valuation_factor | Mac | 是 | 是 | calc_valuation_factor |
| trade_stock_quality_factor | Mac | 是 | 是 | calc_quality_factor |
| trade_stock_factor | Mac | 是 | 是 | calc_technical_factor |
| trade_factor_validation | Mac | 是 | 手动 | validate_factors |
| trade_log_bias_daily | Mac | 是 | 是 | calc_log_bias |
| trade_technical_indicator | Mac | **待改造** | 是 | 原未改造，纳入统一管理 |
| pt_rounds / pt_positions | Mac | 否 | 是 | 模拟交易，仅本地 |
| financial_income/balance/dividend | Mac | 是 | 手动 | 季度更新 |
| bank_asset_quality | Mac | 是 | 手动 | 季度更新 |
| task_runs | Mac | 否 | — | 新增，执行状态记录 |
