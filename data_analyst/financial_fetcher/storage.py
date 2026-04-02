# -*- coding: utf-8 -*-
"""storage layer for financial tables"""

import logging
import sys
import os
import time
from typing import Optional, List

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.db import execute_query, get_connection
from .schemas import ALL_DDL

logger = logging.getLogger(__name__)


def _retry(func, desc: str, max_retries: int = 3, delay: int = 5):
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise
            logger.warning(f"{desc} attempt {attempt} failed: {e}, retry in {delay}s")
            time.sleep(delay)


class FinancialStorage:
    """storage for financial tables"""

    def __init__(self, env: str = 'online'):
        self.env = env

    def init_tables(self):
        """create all tables if not exist"""
        def _do():
            conn = get_connection(self.env)
            cursor = conn.cursor()
            for ddl in ALL_DDL:
                cursor.execute(ddl)
            conn.commit()
            cursor.close()
            conn.close()
        _retry(_do, "init financial tables")
        logger.info("financial tables ready")

    def upsert(self, table: str, records: List[dict]) -> int:
        """generic upsert via INSERT ... ON DUPLICATE KEY UPDATE"""
        if not records:
            return 0
        columns = list(records[0].keys())
        cols_sql = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_sql = ", ".join([f"{c} = VALUES({c})" for c in columns])
        sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_sql}"
        params_list = [tuple(r.get(c) for c in columns) for r in records]

        def _do():
            conn = get_connection(self.env)
            try:
                cursor = conn.cursor()
                cursor.executemany(sql, params_list)
                count = cursor.rowcount
                conn.commit()
                return count
            except Exception as e:
                conn.rollback()
                raise
            finally:
                cursor.close()
                conn.close()
        count = _retry(_do, f"upsert {len(records)} rows into {table}")
        logger.info(f"Upserted {count} rows into {table}")
        return count

    def query(self, sql: str, params: tuple = ()) -> List[dict]:
        """execute query and return list of dicts"""
        return execute_query(sql, params, env=self.env)
