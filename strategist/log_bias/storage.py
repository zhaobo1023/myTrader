# -*- coding: utf-8 -*-
"""storage layer for trade_log_bias_daily"""

import logging
import sys
import os
import time
from typing import Optional

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.db import execute_query, get_connection

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS trade_log_bias_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL COMMENT 'code',
    trade_date DATE NOT NULL COMMENT 'trade date',
    close_price DOUBLE COMMENT 'close price',
    ln_close DOUBLE COMMENT 'ln(close)',
    ema_ln_20 DOUBLE COMMENT 'EMA(ln_close, 20)',
    log_bias DOUBLE COMMENT 'log bias',
    signal_state VARCHAR(20) COMMENT 'signal: overheat/breakout/pullback/normal/stall',
    prev_state VARCHAR(20) COMMENT 'previous state',
    last_breakout_date DATE COMMENT 'last breakout date',
    last_stall_date DATE COMMENT 'last stall date',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date (ts_code, trade_date),
    INDEX idx_date (trade_date),
    INDEX idx_signal (signal_state, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='log bias daily data';
"""

UPSERT_SQL = """
INSERT INTO trade_log_bias_daily
    (ts_code, trade_date, close_price, ln_close, ema_ln_20, log_bias,
     signal_state, prev_state, last_breakout_date, last_stall_date)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    close_price = VALUES(close_price),
    ln_close = VALUES(ln_close),
    ema_ln_20 = VALUES(ema_ln_20),
    log_bias = VALUES(log_bias),
    signal_state = VALUES(signal_state),
    prev_state = VALUES(prev_state),
    last_breakout_date = VALUES(last_breakout_date),
    last_stall_date = VALUES(last_stall_date)
"""


def _retry(func, desc: str, max_retries: int = 3, delay: int = 5):
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise
            logger.warning(f"{desc} attempt {attempt} failed: {e}, retry in {delay}s")
            time.sleep(delay)


class LogBiasStorage:
    """storage for trade_log_bias_daily"""

    def __init__(self, env: str = 'online'):
        self.env = env

    def init_table(self):
        """create table if not exists"""
        def _do():
            conn = get_connection(self.env)
            cursor = conn.cursor()
            cursor.execute(DDL)
            conn.commit()
            cursor.close()
            conn.close()
        _retry(_do, "init trade_log_bias_daily table")
        logger.info("table trade_log_bias_daily ready")

    def save(self, ts_code: str, df: pd.DataFrame) -> int:
        """
        save DataFrame to database

        Args:
            ts_code: ETF code
            df: must have columns [trade_date, close, ln_close, ema_ln, log_bias,
                                   signal_state, prev_state, last_breakout_date, last_stall_date]

        Returns:
            number of rows saved
        """
        if df.empty:
            return 0

        count = 0
        conn = get_connection(self.env)
        try:
            cursor = conn.cursor()
            for _, row in df.iterrows():
                trade_date = row['trade_date']
                if hasattr(trade_date, 'strftime'):
                    trade_date = trade_date.strftime('%Y-%m-%d')
                else:
                    trade_date = str(trade_date)

                params = [
                    ts_code,
                    trade_date,
                    float(row['close']) if pd.notna(row['close']) else None,
                    float(row['ln_close']) if pd.notna(row['ln_close']) else None,
                    float(row['ema_ln']) if pd.notna(row['ema_ln']) else None,
                    float(row['log_bias']) if pd.notna(row['log_bias']) else None,
                    row.get('signal_state', ''),
                    row.get('prev_state', ''),
                    row.get('last_breakout_date'),
                    row.get('last_stall_date'),
                ]
                cursor.execute(UPSERT_SQL, params)
                count += 1
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

        logger.info(f"Saved {count} rows for {ts_code}")
        return count

    def get_latest_date(self, ts_code: str) -> Optional[str]:
        """get latest trade_date for a given ts_code"""
        sql = """
            SELECT MAX(trade_date) as latest
            FROM trade_log_bias_daily
            WHERE ts_code = %s
        """
        rows = execute_query(sql, (ts_code,), env=self.env)
        if rows and rows[0]['latest']:
            return str(rows[0]['latest'])
        return None

    def load_history(self, ts_code: str, start_date: str = None) -> pd.DataFrame:
        """load stored log_bias data for a ts_code"""
        if start_date:
            sql = """
                SELECT * FROM trade_log_bias_daily
                WHERE ts_code = %s AND trade_date >= %s
                ORDER BY trade_date ASC
            """
            rows = execute_query(sql, (ts_code, start_date), env=self.env)
        else:
            sql = """
                SELECT * FROM trade_log_bias_daily
                WHERE ts_code = %s
                ORDER BY trade_date ASC
            """
            rows = execute_query(sql, (ts_code,), env=self.env)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
