# -*- coding: utf-8 -*-
"""
Backtest service - job management, status tracking
"""
import json
import logging
from typing import Optional

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')


def submit_backtest(user_id: int, params: dict) -> dict:
    """
    Create a backtest job record and dispatch to Celery.

    Returns dict with job_id and task_id.
    """
    from api.tasks.backtest import run_backtest

    # Serialize params to JSON string
    params_json = json.dumps(params, ensure_ascii=False)

    # Create job record
    sql = """
        INSERT INTO backtest_jobs (user_id, status, params, created_at, updated_at)
        VALUES (%s, 'pending', %s, NOW(), NOW())
    """
    execute_update(sql, (user_id, params_json))

    # Get the inserted job_id
    result = execute_query(
        "SELECT id FROM backtest_jobs WHERE user_id = %s ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    job_id = result[0]['id']

    # Dispatch to Celery
    task = run_backtest.delay(job_id, params)
    task_id = task.id

    # Update job with task_id
    execute_update(
        "UPDATE backtest_jobs SET task_id = %s WHERE id = %s",
        (task_id, job_id),
    )

    logger.info('[BACKTEST] Job %d submitted, task_id=%s', job_id, task_id)
    return {'job_id': job_id, 'task_id': task_id, 'status': 'pending'}


def get_backtest_status(job_id: int) -> Optional[dict]:
    """Get backtest job status from database."""
    sql = """
        SELECT id as job_id, status, total_return, annual_return,
               max_drawdown, sharpe_ratio, ic, icir,
               result_file, error_msg, created_at, finished_at
        FROM backtest_jobs
        WHERE id = %s
    """
    rows = list(execute_query(sql, (job_id,)))
    if not rows:
        return None
    return rows[0]


def get_backtest_result(job_id: int) -> Optional[dict]:
    """Get backtest job result (only if done)."""
    result = get_backtest_status(job_id)
    if not result or result['status'] != 'done':
        return None
    return result


def get_user_backtests(user_id: int, limit: int = 20) -> list:
    """Get recent backtest jobs for a user."""
    sql = """
        SELECT id as job_id, status, total_return, annual_return,
               max_drawdown, sharpe_ratio, created_at, finished_at
        FROM backtest_jobs
        WHERE user_id = %s
        ORDER BY id DESC
        LIMIT %s
    """
    return list(execute_query(sql, (user_id, limit)))


def get_user_strategies(user_id: int) -> list:
    """Get all strategies for a user."""
    sql = """
        SELECT id, name, description, params, is_active, created_at
        FROM strategies
        WHERE user_id = %s
        ORDER BY id DESC
    """
    return list(execute_query(sql, (user_id,)))


def create_strategy(user_id: int, name: str, description: str = None,
                    params: dict = None) -> int:
    """Create a new strategy record."""
    params_json = json.dumps(params, ensure_ascii=False) if params else None
    sql = """
        INSERT INTO strategies (user_id, name, description, params, created_at, updated_at)
        VALUES (%s, %s, %s, %s, NOW(), NOW())
    """
    execute_update(sql, (user_id, name, description, params_json))

    result = execute_query(
        "SELECT id FROM strategies WHERE user_id = %s ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    return result[0]['id']
