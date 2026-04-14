# -*- coding: utf-8 -*-
"""
Report task service - DB layer for trade_report_task table.
Tracks async Celery report generation jobs.
"""
import logging
from typing import Optional, Dict, Any

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')

_TABLE_ENSURED = False

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trade_report_task (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL UNIQUE COMMENT 'Celery task UUID',
    stock_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(50) NOT NULL,
    report_type VARCHAR(30) NOT NULL COMMENT 'one_pager/comprehensive/fundamental/five_section/technical_report',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/done/failed',
    report_id INT NULL COMMENT 'FK to trade_rag_report.id on success',
    error_msg TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_stock_type_status (stock_code, report_type, status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='Report generation task queue'
"""


def ensure_table() -> None:
    global _TABLE_ENSURED
    if _TABLE_ENSURED:
        return
    try:
        execute_update(_CREATE_TABLE_SQL, env='online')
        _TABLE_ENSURED = True
        logger.info('[report_task] trade_report_task table ensured')
    except Exception as exc:
        logger.error('[report_task] ensure_table failed: %s', exc)
        raise


def create_task(
    task_id: str,
    stock_code: str,
    stock_name: str,
    report_type: str,
) -> Dict[str, Any]:
    ensure_table()
    sql = """
        INSERT INTO trade_report_task (task_id, stock_code, stock_name, report_type, status)
        VALUES (%s, %s, %s, %s, 'pending')
    """
    execute_update(sql, (task_id, stock_code, stock_name, report_type), env='online')
    return {
        'task_id': task_id,
        'stock_code': stock_code,
        'stock_name': stock_name,
        'report_type': report_type,
        'status': 'pending',
    }


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    ensure_table()
    sql = """
        SELECT id, task_id, stock_code, stock_name, report_type, status,
               report_id, error_msg, created_at, updated_at
        FROM trade_report_task
        WHERE task_id = %s
        LIMIT 1
    """
    rows = list(execute_query(sql, (task_id,), env='online'))
    if not rows:
        return None
    r = rows[0]
    return {
        'id': r['id'],
        'task_id': r['task_id'],
        'stock_code': r['stock_code'],
        'stock_name': r['stock_name'],
        'report_type': r['report_type'],
        'status': r['status'],
        'report_id': r['report_id'],
        'error_msg': r['error_msg'],
        'created_at': str(r['created_at']),
        'updated_at': str(r['updated_at']),
    }


def get_latest_task(stock_code: str, report_type: str) -> Optional[Dict[str, Any]]:
    ensure_table()
    sql = """
        SELECT id, task_id, stock_code, stock_name, report_type, status,
               report_id, error_msg, created_at, updated_at
        FROM trade_report_task
        WHERE stock_code = %s AND report_type = %s
        ORDER BY created_at DESC
        LIMIT 1
    """
    rows = list(execute_query(sql, (stock_code, report_type), env='online'))
    if not rows:
        return None
    r = rows[0]
    return {
        'id': r['id'],
        'task_id': r['task_id'],
        'stock_code': r['stock_code'],
        'stock_name': r['stock_name'],
        'report_type': r['report_type'],
        'status': r['status'],
        'report_id': r['report_id'],
        'error_msg': r['error_msg'],
        'created_at': str(r['created_at']),
        'updated_at': str(r['updated_at']),
    }


def update_task_running(task_id: str) -> None:
    sql = """
        UPDATE trade_report_task
        SET status = 'running'
        WHERE task_id = %s
    """
    execute_update(sql, (task_id,), env='online')


def update_task_done(task_id: str, report_id: int) -> None:
    sql = """
        UPDATE trade_report_task
        SET status = 'done', report_id = %s
        WHERE task_id = %s
    """
    execute_update(sql, (report_id, task_id), env='online')


def update_task_failed(task_id: str, error_msg: str) -> None:
    truncated = (error_msg or '')[:1000]
    sql = """
        UPDATE trade_report_task
        SET status = 'failed', error_msg = %s
        WHERE task_id = %s
    """
    execute_update(sql, (truncated, task_id), env='online')
