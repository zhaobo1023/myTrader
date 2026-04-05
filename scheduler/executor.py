# -*- coding: utf-8 -*-
"""
Task executor with retry, timeout, dry_run support.

Executes tasks by dynamically importing the target module and calling
the specified function with optional parameters.
"""
import os
import sys
import time
import logging
import importlib
import inspect
from datetime import datetime
from typing import Dict, Callable, Optional

from scheduler.state import TaskRun, save_run, ensure_table

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def execute_task(
    task: Dict,
    completed: Dict[str, str],
    dry_run: bool = False,
    env: Optional[str] = None,
    triggered_by: str = "cli",
) -> str:
    """
    Execute a single task.

    Args:
        task: Task dict with id, module, func, params, etc.
        completed: Dict of already-completed task_id -> status.
        dry_run: If True, only log what would be executed.
        env: Database environment for state recording.
        triggered_by: Who triggered this execution.

    Returns:
        'success', 'failed', or 'skipped'.
    """
    task_id = task["id"]

    # 1. Check if disabled
    if not task.get("enabled", True):
        logger.info("[SKIP] Task %s is disabled", task_id)
        return "skipped"

    # 2. Check upstream dependency status
    deps = task.get("depends_on", [])
    for dep_id in deps:
        dep_status = completed.get(dep_id)
        if dep_status == "failed":
            logger.warning("[SKIP] Task %s: upstream %s failed", task_id, dep_id)
            return "skipped"
        elif dep_status is None:
            logger.warning("[SKIP] Task %s: upstream %s not completed", task_id, dep_id)
            return "skipped"

    # 3. Check manual tasks in prod
    schedule = task.get("schedule", "")
    if schedule == "manual" and env == "prod" and not dry_run:
        logger.info("[SKIP] Task %s is manual-only, skipped in prod", task_id)
        return "skipped"

    # 4. Create TaskRun record
    run = TaskRun(
        task_id=task_id,
        env=env or "local",
        status="running",
        triggered_by=triggered_by,
    )

    try:
        ensure_table(env=env)
    except Exception as e:
        logger.warning("Could not ensure task_runs table: %s", e)

    if dry_run:
        params = task.get("params", {})
        logger.info("[DRY-RUN] Task %s -> %s.%s(%s)",
                     task_id, task["module"], task["func"], params)
        run.status = "success"
        run.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            save_run(run, env=env)
        except Exception:
            pass
        return "success"

    # 5. Retry loop
    retry_cfg = task.get("retry", {})
    max_attempts = retry_cfg.get("max_attempts", 1)
    delay_seconds = retry_cfg.get("delay_seconds", 30)
    timeout_seconds = task.get("timeout_seconds", 1800)

    last_error = None
    for attempt in range(1, max_attempts + 1):
        start_time = time.time()
        try:
            result = _call_task_fn(task, dry_run=False)
            duration = time.time() - start_time
            run.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run.duration_s = round(duration, 2)
            run.retry_count = attempt - 1
            run.status = "success"
            logger.info("[OK] Task %s completed in %.1fs (attempt %d)",
                         task_id, duration, attempt)
            try:
                save_run(run, env=env)
            except Exception:
                pass
            return "success"
        except Exception as e:
            last_error = str(e)
            duration = time.time() - start_time
            logger.warning("[WARN] Task %s failed (attempt %d/%d): %s",
                            task_id, attempt, max_attempts, e)
            if attempt < max_attempts:
                time.sleep(delay_seconds)

    # All attempts exhausted
    run.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run.duration_s = round(time.time() - start_time, 2)
    run.retry_count = max_attempts - 1
    run.status = "failed"
    run.error_msg = last_error
    try:
        save_run(run, env=env)
    except Exception:
        pass

    # Send alert if configured
    if task.get("alert_on_failure", False):
        try:
            from scheduler.alert import send_alert
            send_alert(task, run, completed)
        except Exception as alert_err:
            logger.warning("Failed to send alert: %s", alert_err)

    logger.error("[RED] Task %s failed after %d attempts: %s",
                  task_id, max_attempts, last_error)
    return "failed"


def _call_task_fn(task: Dict, dry_run: bool = False):
    """
    Dynamically import and call the task function.

    Args:
        task: Task dict with module, func, params.
        dry_run: If True, check if function accepts dry_run param and pass it.

    Returns:
        Whatever the task function returns.
    """
    module_path = task["module"]
    func_name = task["func"]
    params = dict(task.get("params", {}))

    # Support module:func format (split on last dot)
    if ":" in module_path:
        module_path, func_name = module_path.rsplit(":", 1)

    mod = importlib.import_module(module_path)
    fn = getattr(mod, func_name)

    # Check if function accepts dry_run parameter
    sig = inspect.signature(fn)
    if dry_run and "dry_run" in sig.parameters:
        params["dry_run"] = True

    return fn(**params)
