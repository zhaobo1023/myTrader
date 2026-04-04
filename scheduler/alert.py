# -*- coding: utf-8 -*-
"""
Webhook alert notifications for task failures and daily summaries.

Sends alerts to Feishu/Lark webhook. Uses text markers [RED]/[WARN]/[OK]
instead of emoji (MySQL utf8 compatibility).
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _get_webhook_url() -> Optional[str]:
    """
    Get the webhook URL from environment variables.

    Checks ALERT_WEBHOOK_URL first, falls back to FEISHU_WEBHOOK_URL.
    """
    return os.getenv("ALERT_WEBHOOK_URL") or os.getenv("FEISHU_WEBHOOK_URL")


def send_alert(
    task: Dict,
    run: object,
    completed: Dict[str, str],
) -> bool:
    """
    Send a failure alert for a task.

    This function never raises exceptions - failures are logged only.

    Args:
        task: Task dict with id, name, module, func.
        run: TaskRun object.
        completed: Dict of task_id -> status for all completed tasks.

    Returns:
        True if alert was sent successfully, False otherwise.
    """
    url = _get_webhook_url()
    if not url:
        logger.debug("No webhook URL configured, skipping alert")
        return False

    task_id = task.get("id", "unknown")
    task_name = task.get("name", task_id)
    error_msg = getattr(run, "error_msg", "Unknown error")
    retry_count = getattr(run, "retry_count", 0)
    duration_s = getattr(run, "duration_s", 0)

    # Count upstream failures
    upstream_deps = task.get("depends_on", [])
    failed_deps = [d for d in upstream_deps if completed.get(d) == "failed"]

    title = f"[RED] Task Failed: {task_name} ({task_id})"
    content_lines = [
        f"Task: {task_name} ({task_id})",
        f"Module: {task['module']}.{task['func']}",
        f"Error: {error_msg}",
        f"Retry attempts: {retry_count}",
        f"Duration: {duration_s:.1f}s",
    ]
    if failed_deps:
        content_lines.append(f"Failed upstream: {', '.join(failed_deps)}")

    content = "\n".join(content_lines)

    return _post_webhook(url, title, content)


def send_daily_summary(summary: List[Dict], env: str = "local") -> bool:
    """
    Send a daily execution summary.

    Args:
        summary: List of dicts from state.today_summary().
        env: Environment name.

    Returns:
        True if alert was sent successfully.
    """
    url = _get_webhook_url()
    if not url:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    title = f"[OK] Scheduler Daily Summary ({today})"

    if not summary:
        content = "No tasks executed today."
        return _post_webhook(url, title, content)

    # Group by task_id
    task_map = {}
    for row in summary:
        tid = row["task_id"]
        if tid not in task_map:
            task_map[tid] = {}
        task_map[tid][row["status"]] = row["cnt"]

    lines = [f"Environment: {env}", ""]
    success_tasks = []
    failed_tasks = []
    for tid, statuses in task_map.items():
        if "failed" in statuses:
            failed_tasks.append(tid)
        elif "success" in statuses:
            success_tasks.append(tid)

    if success_tasks:
        lines.append(f"[OK] Success ({len(success_tasks)}):")
        for tid in success_tasks:
            lines.append(f"  - {tid}")

    if failed_tasks:
        lines.append(f"\n[RED] Failed ({len(failed_tasks)}):")
        for tid in failed_tasks:
            lines.append(f"  - {tid}")

    content = "\n".join(lines)
    return _post_webhook(url, title, content)


def _post_webhook(url: str, title: str, content: str) -> bool:
    """
    POST a message to the webhook URL.

    Returns True on success, False on failure. Never raises.
    """
    payload = {
        "msg_type": "text",
        "content": {"text": f"{title}\n\n{content}"},
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.debug("Webhook alert sent: %s", title)
        return True
    except Exception as e:
        logger.warning("Failed to send webhook alert: %s", e)
        return False
