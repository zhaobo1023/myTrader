# -*- coding: utf-8 -*-
"""
Task run logger -- records each computation task's execution status
into the trade_task_run_log table.

Usage:
    from scheduler.task_logger import TaskLogger

    with TaskLogger('calc_basic_factor', 'factor') as tl:
        count = do_work()
        tl.set_record_count(count)
"""
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL -- executed lazily on first use
# ---------------------------------------------------------------------------
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trade_task_run_log (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_date     DATE NOT NULL          COMMENT '运行日期(目标交易日)',
    task_name    VARCHAR(80) NOT NULL   COMMENT '任务标识',
    task_group   VARCHAR(30) NOT NULL   COMMENT '分组: data_fetch / factor / indicator / strategy / report / sentiment',
    status       VARCHAR(20) NOT NULL   COMMENT 'running / success / failed / skipped',
    started_at   DATETIME NOT NULL      COMMENT '开始时间',
    finished_at  DATETIME               COMMENT '结束时间',
    duration_ms  INT                    COMMENT '耗时(毫秒)',
    record_count INT                    COMMENT '产出记录数',
    error_msg    TEXT                   COMMENT '失败时的错误信息',
    detail       JSON                   COMMENT '额外明细',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_run_date (run_date),
    INDEX idx_task_name (task_name),
    INDEX idx_status (status),
    UNIQUE KEY uk_date_task (run_date, task_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务运行日志'
"""

_table_ensured = False


def _ensure_table(env: str = 'online'):
    """Create the table if it does not exist yet (idempotent)."""
    global _table_ensured
    if _table_ensured:
        return
    try:
        from config.db import execute_update
        execute_update(_CREATE_TABLE_SQL, env=env)
        _table_ensured = True
    except Exception as e:
        logger.warning("Failed to ensure trade_task_run_log table: %s", e)


class TaskLogger:
    """Context manager that logs task execution to trade_task_run_log."""

    def __init__(self, task_name: str, task_group: str,
                 run_date: str = None, env: str = 'online'):
        self.task_name = task_name
        self.task_group = task_group
        self.run_date = run_date or date.today().isoformat()
        self.env = env
        self._record_count = None
        self._detail = None
        self._started_at = None

    # -- setters (call inside the `with` block) --

    def set_record_count(self, count: int):
        self._record_count = count

    def set_detail(self, detail: dict):
        self._detail = detail

    # -- context manager --

    def __enter__(self):
        _ensure_table(self.env)
        self._started_at = datetime.now()
        self._upsert('running')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        finished_at = datetime.now()
        duration_ms = int((finished_at - self._started_at).total_seconds() * 1000)

        if exc_type is None:
            self._upsert('success', finished_at=finished_at,
                          duration_ms=duration_ms)
        else:
            err_msg = f"{exc_type.__name__}: {exc_val}"
            # Truncate to 4000 chars to avoid TEXT overflow edge cases
            if len(err_msg) > 4000:
                err_msg = err_msg[:4000]
            self._upsert('failed', finished_at=finished_at,
                          duration_ms=duration_ms, error_msg=err_msg)

        # Do NOT suppress exceptions -- let them propagate
        return False

    # -- internals --

    def _upsert(self, status: str, finished_at: datetime = None,
                duration_ms: int = None, error_msg: str = None):
        import json
        from config.db import execute_update

        detail_json = json.dumps(self._detail, ensure_ascii=False) if self._detail else None

        sql = """
            INSERT INTO trade_task_run_log
                (run_date, task_name, task_group, status, started_at,
                 finished_at, duration_ms, record_count, error_msg, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                status       = VALUES(status),
                started_at   = VALUES(started_at),
                finished_at  = VALUES(finished_at),
                duration_ms  = VALUES(duration_ms),
                record_count = VALUES(record_count),
                error_msg    = VALUES(error_msg),
                detail       = VALUES(detail)
        """
        params = (
            self.run_date,
            self.task_name,
            self.task_group,
            status,
            self._started_at.strftime('%Y-%m-%d %H:%M:%S') if self._started_at else None,
            finished_at.strftime('%Y-%m-%d %H:%M:%S') if finished_at else None,
            duration_ms,
            self._record_count,
            error_msg,
            detail_json,
        )

        try:
            execute_update(sql, params, env=self.env)
        except Exception as e:
            logger.warning("TaskLogger._upsert failed for %s: %s",
                           self.task_name, e)
