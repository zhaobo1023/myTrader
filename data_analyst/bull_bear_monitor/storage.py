# -*- coding: utf-8 -*-
"""牛熊信号存储层"""
import logging
import time
from typing import List, Optional
from config.db import execute_query, get_connection
from .schemas import BULL_BEAR_SIGNAL_DDL, BullBearSignal

logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO trade_bull_bear_signal
    (calc_date, cn_10y_value, cn_10y_ma20, cn_10y_trend, cn_10y_signal,
     usdcny_value, usdcny_ma20, usdcny_trend, usdcny_signal,
     dividend_relative, dividend_rel_ma20, dividend_trend, dividend_signal,
     composite_score, regime)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    cn_10y_value = VALUES(cn_10y_value),
    cn_10y_ma20 = VALUES(cn_10y_ma20),
    cn_10y_trend = VALUES(cn_10y_trend),
    cn_10y_signal = VALUES(cn_10y_signal),
    usdcny_value = VALUES(usdcny_value),
    usdcny_ma20 = VALUES(usdcny_ma20),
    usdcny_trend = VALUES(usdcny_trend),
    usdcny_signal = VALUES(usdcny_signal),
    dividend_relative = VALUES(dividend_relative),
    dividend_rel_ma20 = VALUES(dividend_rel_ma20),
    dividend_trend = VALUES(dividend_trend),
    dividend_signal = VALUES(dividend_signal),
    composite_score = VALUES(composite_score),
    regime = VALUES(regime)
"""

MAX_RETRIES = 3
RETRY_DELAY = 5


class BullBearStorage:
    @staticmethod
    def init_table():
        _retry_operation(
            lambda: BullBearStorage._init_table_inner(),
            "init trade_bull_bear_signal table"
        )

    @staticmethod
    def _init_table_inner():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(BULL_BEAR_SIGNAL_DDL)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("trade_bull_bear_signal table initialized")

    @staticmethod
    def _signal_to_params(signal: BullBearSignal) -> list:
        return [
            signal.calc_date,
            signal.cn_10y_value, signal.cn_10y_ma20, signal.cn_10y_trend, signal.cn_10y_signal,
            signal.usdcny_value, signal.usdcny_ma20, signal.usdcny_trend, signal.usdcny_signal,
            signal.dividend_relative, signal.dividend_rel_ma20, signal.dividend_trend, signal.dividend_signal,
            signal.composite_score, signal.regime,
        ]

    @staticmethod
    def save_batch(signals: List[BullBearSignal]):
        if not signals:
            return
        _retry_operation(
            lambda: BullBearStorage._save_batch_inner(signals),
            f"save {len(signals)} bull/bear signals"
        )

    @staticmethod
    def _save_batch_inner(signals: List[BullBearSignal]):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            for signal in signals:
                cursor.execute(UPSERT_SQL, BullBearStorage._signal_to_params(signal))
            conn.commit()
            logger.info(f"Saved {len(signals)} bull/bear signals")
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_latest_regime() -> Optional[dict]:
        rows = execute_query(
            "SELECT * FROM trade_bull_bear_signal ORDER BY calc_date DESC LIMIT 1"
        )
        return rows[0] if rows else None

    @staticmethod
    def load_signals(start_date: str = None, end_date: str = None) -> list:
        sql = "SELECT * FROM trade_bull_bear_signal WHERE 1=1"
        params = []
        if start_date:
            sql += " AND calc_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND calc_date <= %s"
            params.append(end_date)
        sql += " ORDER BY calc_date ASC"
        return execute_query(sql, tuple(params) if params else ())


def _retry_operation(func, description: str, max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            is_last = attempt == max_retries
            logger.warning(
                f"{description} failed (attempt {attempt}/{max_retries}): {e}"
                + ("" if is_last else f", retrying in {delay}s...")
            )
            if is_last:
                break
            time.sleep(delay)
    logger.error(f"{description} final failure: {last_error}")
    raise last_error
