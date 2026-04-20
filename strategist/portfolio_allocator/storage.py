# -*- coding: utf-8 -*-
"""策略权重存储层"""
import logging
import time
from typing import List, Optional
from config.db import execute_query, get_connection
from .schemas import STRATEGY_WEIGHTS_DDL, StrategyWeight

logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO trade_strategy_weights
    (calc_date, strategy_name, base_weight, regime_adjustment, crowding_adjustment,
     final_weight, regime, crowding_level)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    base_weight = VALUES(base_weight),
    regime_adjustment = VALUES(regime_adjustment),
    crowding_adjustment = VALUES(crowding_adjustment),
    final_weight = VALUES(final_weight),
    regime = VALUES(regime),
    crowding_level = VALUES(crowding_level)
"""

MAX_RETRIES = 3
RETRY_DELAY = 5


class WeightStorage:
    @staticmethod
    def init_table():
        _retry_operation(
            lambda: WeightStorage._init_table_inner(),
            "init trade_strategy_weights table"
        )
    
    @staticmethod
    def _init_table_inner():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(STRATEGY_WEIGHTS_DDL)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("trade_strategy_weights table initialized")
    
    @staticmethod
    def _weight_to_params(w: StrategyWeight) -> list:
        return [
            w.calc_date, w.strategy_name, w.base_weight,
            w.regime_adjustment, w.crowding_adjustment,
            w.final_weight, w.regime, w.crowding_level,
        ]
    
    @staticmethod
    def save_batch(weights: List[StrategyWeight]):
        if not weights:
            return
        _retry_operation(
            lambda: WeightStorage._save_batch_inner(weights),
            f"save {len(weights)} strategy weights"
        )
    
    @staticmethod
    def _save_batch_inner(weights: List[StrategyWeight]):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            for w in weights:
                cursor.execute(UPSERT_SQL, WeightStorage._weight_to_params(w))
            conn.commit()
            logger.info(f"Saved {len(weights)} strategy weights")
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def get_latest_weights() -> list:
        rows = execute_query(
            """SELECT * FROM trade_strategy_weights 
               WHERE calc_date = (SELECT MAX(calc_date) FROM trade_strategy_weights)
               ORDER BY strategy_name"""
        )
        return rows
    
    @staticmethod
    def load_weights(start_date: str = None, end_date: str = None) -> list:
        sql = "SELECT * FROM trade_strategy_weights WHERE 1=1"
        params = []
        if start_date:
            sql += " AND calc_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND calc_date <= %s"
            params.append(end_date)
        sql += " ORDER BY calc_date ASC, strategy_name"
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
