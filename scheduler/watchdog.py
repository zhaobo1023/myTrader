# -*- coding: utf-8 -*-
"""
Scheduler watchdog: detects missed/stale runs and triggers retry + alert.

A "missed run" is a task that:
  - Has a concrete scheduled time (HH:MM) today
  - Is enabled in prod
  - Has no successful run recorded today AND no currently-running run
  - The scheduled time has passed by more than GRACE_MINUTES

Run this from a cron job or call check_missed_runs() periodically:
  python -m scheduler.watchdog
"""
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Minutes after scheduled time before we declare a run "missed"
GRACE_MINUTES = 30


def _parse_hhmm(schedule: str) -> Optional[datetime]:
    """Parse 'HH:MM' schedule string into today's datetime, or None."""
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', schedule.strip())
    if not m:
        return None
    now = datetime.now()
    return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)


def _today_runs(env: str = 'local') -> Dict[str, str]:
    """Return {task_id: best_status} for all runs today."""
    from config.db import execute_query
    rows = execute_query(
        """
        SELECT task_id, status
        FROM task_runs
        WHERE DATE(started_at) = CURDATE()
        ORDER BY started_at ASC
        """,
        env=env,
    )
    # Keep the "best" status: running > success > failed > skipped
    priority = {'running': 4, 'success': 3, 'failed': 2, 'skipped': 1}
    result: Dict[str, str] = {}
    for r in rows:
        tid, st = r['task_id'], r['status']
        if priority.get(st, 0) > priority.get(result.get(tid, ''), 0):
            result[tid] = st
    return result


def check_missed_runs(env: str = 'local', dry_run: bool = False) -> List[Dict]:
    """
    Scan all scheduled tasks and detect missed runs.

    Returns a list of missed task dicts (augmented with 'missed_by_minutes').
    Also triggers retry and sends alert for each missed task.
    """
    from scheduler.loader import load_tasks

    tasks = load_tasks()
    today_statuses = _today_runs(env=env)
    now = datetime.now()
    missed = []

    for task in tasks:
        if not task.get('enabled', True):
            continue
        schedule = task.get('schedule', '')
        scheduled_dt = _parse_hhmm(schedule)
        if scheduled_dt is None:
            # after_gate / manual / cron — skip time-based check
            continue

        deadline = scheduled_dt + timedelta(minutes=GRACE_MINUTES)
        if now < deadline:
            # Not yet past grace window
            continue

        status = today_statuses.get(task['id'])
        if status in ('success', 'running'):
            continue

        missed_by = int((now - deadline).total_seconds() / 60)
        task_info = dict(task)
        task_info['missed_by_minutes'] = missed_by
        task_info['last_status_today'] = status  # 'failed', 'skipped', or None
        missed.append(task_info)
        logger.warning(
            '[WATCHDOG] Missed run: %s (scheduled %s, missed by %d min, last=%s)',
            task['id'], schedule, missed_by, status,
        )

        if dry_run:
            continue

        # --- Retry ---
        _retry_missed(task, env=env)

        # --- Alert ---
        _alert_missed(task, missed_by, status)

    if missed:
        logger.warning('[WATCHDOG] %d missed task(s) detected', len(missed))
    else:
        logger.info('[WATCHDOG] All scheduled tasks ran on time')

    return missed


def _retry_missed(task: Dict, env: str = 'local') -> None:
    """Attempt to re-run a missed task (best-effort, non-blocking)."""
    from scheduler.loader import load_tasks
    from scheduler.executor import execute_task

    task_id = task['id']
    logger.info('[WATCHDOG] Retrying missed task: %s', task_id)

    # Build a minimal completed dict: mark deps as success so we don't block
    # (if deps really failed, the retry will fail too — that's fine)
    completed: Dict[str, str] = {}
    for dep_id in task.get('depends_on', []):
        completed[dep_id] = 'success'

    try:
        result = execute_task(
            task,
            completed=completed,
            dry_run=False,
            env=env,
            triggered_by='watchdog',
        )
        logger.info('[WATCHDOG] Retry result for %s: %s', task_id, result)
    except Exception as e:
        logger.error('[WATCHDOG] Retry execution error for %s: %s', task_id, e)


def _alert_missed(task: Dict, missed_by_minutes: int, last_status: Optional[str]) -> None:
    """Send a missed-run alert via webhook."""
    from scheduler.alert import _get_webhook_url, _post_webhook
    url = _get_webhook_url()
    if not url:
        return

    task_id = task.get('id', 'unknown')
    task_name = task.get('name', task_id)
    schedule = task.get('schedule', '')
    status_str = last_status or '未执行'

    title = f'[WARN] 任务漏执行: {task_name}'
    content = (
        f'任务ID: {task_id}\n'
        f'计划时间: {schedule}\n'
        f'已超时: {missed_by_minutes} 分钟\n'
        f'今日状态: {status_str}\n'
        f'触发来源: watchdog\n'
        f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    )
    _post_webhook(url, title, content)


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    env = os.getenv('DB_ENV', 'local')
    dry = '--dry-run' in sys.argv
    missed = check_missed_runs(env=env, dry_run=dry)
    print(f'Missed runs: {len(missed)}')
    for t in missed:
        print(f"  - {t['id']} (scheduled {t.get('schedule')}, missed by {t['missed_by_minutes']}min)")
    sys.exit(1 if missed else 0)
