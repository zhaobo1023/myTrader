# -*- coding: utf-8 -*-
"""
SVD 市场状态存储层 - 数据库读写
"""
import logging
from datetime import date
from typing import List, Optional

from config.db import execute_query, get_connection, execute_update
from .schemas import SVD_MARKET_STATE_DDL, SVDRecord, WindowSVDResult, MarketRegime

logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO trade_svd_market_state
    (calc_date, window_size, top1_var_ratio, top3_var_ratio, top5_var_ratio,
     reconstruction_error, market_state, stock_count, is_mutation)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    top1_var_ratio = VALUES(top1_var_ratio),
    top3_var_ratio = VALUES(top3_var_ratio),
    top5_var_ratio = VALUES(top5_var_ratio),
    reconstruction_error = VALUES(reconstruction_error),
    market_state = VALUES(market_state),
    stock_count = VALUES(stock_count),
    is_mutation = VALUES(is_mutation)
"""


class SVDStorage:
    """SVD 市场状态存储"""

    @staticmethod
    def init_table():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(SVD_MARKET_STATE_DDL)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("trade_svd_market_state 表已初始化")

    @staticmethod
    def save_record(record: SVDRecord):
        execute_update(UPSERT_SQL, [
            record.calc_date, record.window_size,
            record.top1_var_ratio, record.top3_var_ratio, record.top5_var_ratio,
            record.reconstruction_error, record.market_state,
            record.stock_count, record.is_mutation,
        ])

    @staticmethod
    def save_batch(records: List[SVDRecord]):
        if not records:
            return
        conn = get_connection()
        cursor = conn.cursor()
        for record in records:
            cursor.execute(UPSERT_SQL, [
                record.calc_date, record.window_size,
                record.top1_var_ratio, record.top3_var_ratio, record.top5_var_ratio,
                record.reconstruction_error, record.market_state,
                record.stock_count, record.is_mutation,
            ])
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"批量保存 {len(records)} 条 SVD 记录")

    @staticmethod
    def load_results(start_date: str = None, end_date: str = None) -> list:
        sql = "SELECT * FROM trade_svd_market_state WHERE 1=1"
        params = []
        if start_date:
            sql += " AND calc_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND calc_date <= %s"
            params.append(end_date)
        sql += " ORDER BY calc_date ASC, window_size ASC"
        return execute_query(sql, params or ())

    @staticmethod
    def get_latest_state(window_size: int = 120) -> Optional[dict]:
        rows = execute_query(
            "SELECT * FROM trade_svd_market_state "
            "WHERE window_size = %s ORDER BY calc_date DESC LIMIT 1",
            [window_size]
        )
        return rows[0] if rows else None
