# -*- coding: utf-8 -*-
"""
RAG report service - DB cache layer for comprehensive reports.
"""
import logging
from datetime import date
from typing import Optional, Dict, Any

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')


def get_today_report(stock_code: str, report_type: str = 'comprehensive') -> Optional[Dict[str, Any]]:
    """
    Return today's cached report for this stock, or None if not generated yet.
    """
    today = date.today().isoformat()
    sql = """
        SELECT id, stock_code, stock_name, report_type, report_date, content, created_at
        FROM trade_rag_report
        WHERE stock_code = %s AND report_type = %s AND report_date = %s
        LIMIT 1
    """
    rows = list(execute_query(sql, (stock_code, report_type, today)))
    if not rows:
        return None
    row = rows[0]
    return {
        'id': row['id'],
        'stock_code': row['stock_code'],
        'stock_name': row['stock_name'],
        'report_type': row['report_type'],
        'report_date': str(row['report_date']),
        'content': row['content'],
        'created_at': str(row['created_at']),
    }


def save_report(
    stock_code: str,
    stock_name: str,
    report_type: str,
    content: str,
) -> int:
    """
    Save (or replace) the report for today. Returns the row id.
    """
    today = date.today().isoformat()
    sql = """
        INSERT INTO trade_rag_report (stock_code, stock_name, report_type, report_date, content)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            stock_name = VALUES(stock_name),
            content = VALUES(content),
            created_at = NOW()
    """
    execute_update(sql, (stock_code, stock_name, report_type, today, content))

    # Fetch the id after upsert
    id_sql = """
        SELECT id FROM trade_rag_report
        WHERE stock_code = %s AND report_type = %s AND report_date = %s
        LIMIT 1
    """
    rows = list(execute_query(id_sql, (stock_code, report_type, today)))
    return rows[0]['id'] if rows else 0


def list_recent_reports(stock_code: str, limit: int = 5) -> list:
    """Return recent rag reports for a stock, newest first."""
    sql = """
        SELECT id, stock_code, stock_name, report_type, report_date, created_at
        FROM trade_rag_report
        WHERE stock_code = %s
        ORDER BY report_date DESC, created_at DESC
        LIMIT %s
    """
    rows = list(execute_query(sql, (stock_code, limit)))
    return [
        {
            'id': r['id'],
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'],
            'report_type': r['report_type'],
            'report_date': str(r['report_date']),
            'created_at': str(r['created_at']),
        }
        for r in rows
    ]


def get_report_content(report_id: int) -> Optional[str]:
    """Return Markdown content of a report by id."""
    sql = "SELECT content FROM trade_rag_report WHERE id = %s LIMIT 1"
    rows = list(execute_query(sql, (report_id,)))
    if not rows:
        return None
    return rows[0]['content']
