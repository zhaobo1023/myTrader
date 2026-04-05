# -*- coding: utf-8 -*-
"""
SVD 市场状态存储层 - 数据库读写 (含重试逻辑 + 备用IP自动切换)
"""
import logging
import time
import os
from datetime import date
from typing import List, Optional

import pymysql
from config.db import execute_query, get_connection, execute_update, execute_dual_update, ONLINE_DB_CONFIG, get_dual_connections
from .schemas import SVD_MARKET_STATE_DDL, SVDRecord, WindowSVDResult, MarketRegime

logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO trade_svd_market_state
    (calc_date, window_size, universe_type, universe_id,
     top1_var_ratio, top3_var_ratio, top5_var_ratio,
     reconstruction_error, market_state, stock_count, is_mutation)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    top1_var_ratio = VALUES(top1_var_ratio),
    top3_var_ratio = VALUES(top3_var_ratio),
    top5_var_ratio = VALUES(top5_var_ratio),
    reconstruction_error = VALUES(reconstruction_error),
    market_state = VALUES(market_state),
    stock_count = VALUES(stock_count),
    is_mutation = VALUES(is_mutation)
"""

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒

# 备用 DB IP (当主 IP 不可达时自动尝试)
FALLBACK_HOSTS = os.getenv('SVD_FALLBACK_HOSTS', '').split(',')
FALLBACK_HOSTS = [h.strip() for h in FALLBACK_HOSTS if h.strip()]


def _probe_connection(host: str, config: dict, timeout: int = 5) -> bool:
    """快速探测 DB 连通性"""
    try:
        probe_config = {**config, 'host': host, 'connect_timeout': timeout}
        conn = pymysql.connect(**probe_config)
        conn.close()
        return True
    except Exception:
        return False


def _ensure_connection(config: dict) -> dict:
    """
    确保 DB 可达，不通则尝试备用 IP

    Returns:
        可用的 DB 配置字典
    """
    primary_host = config.get('host', '')
    if _probe_connection(primary_host, config):
        return config

    # 主 IP 不通，尝试备用
    for fallback_host in FALLBACK_HOSTS:
        if fallback_host == primary_host:
            continue
        logger.info(f"主 IP {primary_host} 不通，尝试备用 {fallback_host}...")
        if _probe_connection(fallback_host, config):
            logger.info(f"备用 IP {fallback_host} 可达，切换连接")
            return {**config, 'host': fallback_host}

    # 所有都不通，仍返回原始配置 (让重试逻辑处理)
    return config


class SVDStorage:
    """SVD 市场状态存储"""

    @staticmethod
    def init_table():
        _retry_operation(
            lambda: SVDStorage._init_table_inner(),
            "初始化 trade_svd_market_state 表"
        )

    @staticmethod
    def _init_table_inner():
        from config.db import get_current_env
        if get_current_env() == 'online':
            live_config = _ensure_connection(ONLINE_DB_CONFIG)
        else:
            live_config = None

        conn = get_connection()
        if live_config and live_config.get('host') != ONLINE_DB_CONFIG.get('host'):
            conn.close()
            conn = pymysql.connect(**live_config)
            logger.info(f"使用备用 IP {live_config['host']} 初始化表")

        cursor = conn.cursor()
        cursor.execute(SVD_MARKET_STATE_DDL)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("trade_svd_market_state 表已初始化")

    @staticmethod
    def _record_to_params(record: SVDRecord) -> list:
        """将 SVDRecord 转为 SQL 参数列表"""
        return [
            record.calc_date, record.window_size,
            record.universe_type, record.universe_id,
            record.top1_var_ratio, record.top3_var_ratio, record.top5_var_ratio,
            record.reconstruction_error, record.market_state,
            record.stock_count, record.is_mutation,
        ]

    @staticmethod
    def save_record(record: SVDRecord):
        _retry_operation(
            lambda: execute_dual_update(UPSERT_SQL, SVDStorage._record_to_params(record)),
            f"保存 SVD 记录 {record.calc_date} w={record.window_size}"
        )

    @staticmethod
    def save_batch(records: List[SVDRecord]):
        if not records:
            return
        _retry_operation(
            lambda: SVDStorage._save_batch_inner(records),
            f"批量保存 {len(records)} 条 SVD 记录"
        )

    @staticmethod
    def _save_batch_inner(records: List[SVDRecord]):
        # 保存前探测连接，自动切换备用 IP
        from config.db import get_current_env
        if get_current_env() == 'online':
            live_config = _ensure_connection(ONLINE_DB_CONFIG)
        else:
            live_config = None

        conn = get_connection()
        # 如果探测到可用备用 IP 且与当前不同，用新配置重建连接
        if live_config and live_config.get('host') != ONLINE_DB_CONFIG.get('host'):
            conn.close()
            conn = pymysql.connect(**live_config)
            logger.info(f"使用备用 IP {live_config['host']} 保存")

        cursor = conn.cursor()
        try:
            for record in records:
                cursor.execute(UPSERT_SQL, SVDStorage._record_to_params(record))
            conn.commit()
            logger.info(f"批量保存 {len(records)} 条 SVD 记录")
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

        # Dual-write to secondary (best-effort)
        conn2 = None
        try:
            _, conn2 = get_dual_connections()
        except Exception:
            pass
        if conn2:
            try:
                cursor2 = conn2.cursor()
                for record in records:
                    cursor2.execute(UPSERT_SQL, SVDStorage._record_to_params(record))
                conn2.commit()
                cursor2.close()
            except Exception as e:
                logger.warning("Dual-write _save_batch_inner failed: %s", e)
            finally:
                conn2.close()

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


def _retry_operation(func, description: str, max_retries: int = MAX_RETRIES,
                     delay: float = RETRY_DELAY):
    """通用重试逻辑，处理 VPN/网络断连"""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            is_last = attempt == max_retries
            logger.warning(
                f"{description} 失败 (第 {attempt}/{max_retries} 次): {e}"
                + ("" if is_last else f", {delay}s 后重试...")
            )
            if is_last:
                break
            time.sleep(delay)
    logger.error(f"{description} 最终失败: {last_error}")
    raise last_error
