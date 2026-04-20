# -*- coding: utf-8 -*-
"""拥挤度分数存储层"""
import logging
import time
from typing import List, Optional
from config.db import execute_query, get_connection
from .schemas import CROWDING_SCORE_DDL, CrowdingScore

logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO trade_crowding_score
    (calc_date, dimension, dimension_id, turnover_hhi, turnover_hhi_percentile,
     northbound_deviation, margin_concentration, svd_top1_ratio,
     crowding_score, crowding_level)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    turnover_hhi = VALUES(turnover_hhi),
    turnover_hhi_percentile = VALUES(turnover_hhi_percentile),
    northbound_deviation = VALUES(northbound_deviation),
    margin_concentration = VALUES(margin_concentration),
    svd_top1_ratio = VALUES(svd_top1_ratio),
    crowding_score = VALUES(crowding_score),
    crowding_level = VALUES(crowding_level)
"""

MAX_RETRIES = 3
RETRY_DELAY = 5


class CrowdingStorage:
    @staticmethod
    def init_table():
        _retry_operation(
            lambda: CrowdingStorage._init_table_inner(),
            "init trade_crowding_score table"
        )
    
    @staticmethod
    def _init_table_inner():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(CROWDING_SCORE_DDL)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("trade_crowding_score table initialized")
    
    @staticmethod
    def _score_to_params(score: CrowdingScore) -> list:
        return [
            score.calc_date, score.dimension, score.dimension_id,
            score.turnover_hhi, score.turnover_hhi_percentile,
            score.northbound_deviation, score.margin_concentration, score.svd_top1_ratio,
            score.crowding_score, score.crowding_level,
        ]
    
    @staticmethod
    def save_batch(scores: List[CrowdingScore]):
        if not scores:
            return
        _retry_operation(
            lambda: CrowdingStorage._save_batch_inner(scores),
            f"save {len(scores)} crowding scores"
        )
    
    @staticmethod
    def _save_batch_inner(scores: List[CrowdingScore]):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            for score in scores:
                cursor.execute(UPSERT_SQL, CrowdingStorage._score_to_params(score))
            conn.commit()
            logger.info(f"Saved {len(scores)} crowding scores")
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def get_latest_score(dimension: str = 'overall') -> Optional[dict]:
        rows = execute_query(
            "SELECT * FROM trade_crowding_score WHERE dimension = %s ORDER BY calc_date DESC LIMIT 1",
            (dimension,)
        )
        return rows[0] if rows else None
    
    @staticmethod
    def load_scores(start_date: str = None, end_date: str = None, dimension: str = None) -> list:
        sql = "SELECT * FROM trade_crowding_score WHERE 1=1"
        params = []
        if start_date:
            sql += " AND calc_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND calc_date <= %s"
            params.append(end_date)
        if dimension:
            sql += " AND dimension = %s"
            params.append(dimension)
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
