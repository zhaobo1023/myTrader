# -*- coding: utf-8 -*-
"""
Task execution state persistence.

Uses pymysql (config.db) to store task run records.
"""
import os
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict

from config.db import execute_query, execute_update

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class TaskRun:
    """Record of a single task execution."""
    task_id: str
    env: str = "local"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str = "pending"  # pending / running / success / failed / skipped
    duration_s: float = 0.0
    error_msg: Optional[str] = None
    retry_count: int = 0
    triggered_by: str = "cli"

    def __post_init__(self):
        if self.started_at is None:
            self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


CREATE_TABLE_SQL = """
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
"""


def ensure_table(env=None):
    """Create the task_runs table if it does not exist."""
    execute_update(CREATE_TABLE_SQL, env=env)
    logger.info("task_runs table ensured (env=%s)", env or "default")


def save_run(run: TaskRun, env=None):
    """Insert a TaskRun record into the database."""
    sql = """
        INSERT INTO task_runs
            (task_id, env, started_at, finished_at, status, duration_s,
             error_msg, retry_count, triggered_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        run.task_id,
        run.env,
        run.started_at,
        run.finished_at,
        run.status,
        run.duration_s,
        run.error_msg,
        run.retry_count,
        run.triggered_by,
    )
    execute_update(sql, params, env=env)


def recent_runs(task_id: str, n: int = 10, env=None) -> List[Dict]:
    """Return the most recent n runs for a task."""
    sql = """
        SELECT id, task_id, env, started_at, finished_at, status,
               duration_s, error_msg, retry_count, triggered_by
        FROM task_runs
        WHERE task_id = %s
        ORDER BY started_at DESC
        LIMIT %s
    """
    return execute_query(sql, (task_id, n), env=env)


def today_summary(env=None) -> List[Dict]:
    """Return today's task run summary."""
    sql = """
        SELECT task_id, status, COUNT(*) AS cnt,
               ROUND(AVG(duration_s), 1) AS avg_duration_s,
               MAX(error_msg) AS last_error
        FROM task_runs
        WHERE DATE(started_at) = CURDATE()
        GROUP BY task_id, status
        ORDER BY task_id, FIELD(status, 'failed', 'success', 'skipped', 'running', 'pending')
    """
    return execute_query(sql, env=env)
