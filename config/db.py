# -*- coding: utf-8 -*-
"""
MySQL 数据库连接器 - 支持本地/线上双环境

配置从 .env 文件读取
- LOCAL_* 环境变量：本地开发环境
- ONLINE_* 环境变量：线上生产环境（从原 quant 项目复制）

使用方式：
    from config.db import get_connection, get_local_connection, get_online_connection

    # 默认使用本地环境
    conn = get_connection()

    # 显式指定环境
    conn = get_local_connection()
    conn = get_online_connection()
"""
import os
import time
import logging
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
from typing import Optional, Tuple

# 加载 .env 文件
load_dotenv()

# 当前环境: 'local' 或 'online'
CURRENT_ENV = os.getenv('DB_ENV', 'local')

# Dual-write config
DUAL_WRITE = os.getenv('DUAL_WRITE', 'false').lower() == 'true'
DUAL_WRITE_TARGET = os.getenv('DUAL_WRITE_TARGET', 'online')

logger = logging.getLogger(__name__)


def _build_db_config(prefix: str) -> dict:
    """
    根据前缀构建数据库配置

    Args:
        prefix: 环境前缀，如 'LOCAL' 或 'ONLINE'

    Returns:
        数据库配置字典
    """
    return {
        'host': os.getenv(f'{prefix}_DB_HOST', 'localhost'),
        'port': int(os.getenv(f'{prefix}_DB_PORT', '3306')),
        'user': os.getenv(f'{prefix}_DB_USER', 'root'),
        'password': os.getenv(f'{prefix}_DB_PASSWORD', ''),
        'database': os.getenv(f'{prefix}_DB_NAME', 'mytrader'),
        'charset': 'utf8mb4',
        'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '5')),
    }


# 本地环境配置
LOCAL_DB_CONFIG = _build_db_config('LOCAL')

# 线上环境配置（从 quant 项目迁移）
ONLINE_DB_CONFIG = _build_db_config('ONLINE')

# 默认配置（根据 CURRENT_ENV）
DB_CONFIG = LOCAL_DB_CONFIG if CURRENT_ENV == 'local' else ONLINE_DB_CONFIG


def get_connection(env: Optional[str] = None):
    """
    获取数据库连接

    Args:
        env: 指定环境 'local' 或 'online'，默认使用 CURRENT_ENV

    Returns:
        pymysql 连接对象
    """
    if env == 'local':
        config = LOCAL_DB_CONFIG
    elif env == 'online':
        config = ONLINE_DB_CONFIG
    else:
        config = DB_CONFIG
    return pymysql.connect(**config)


def get_local_connection():
    """获取本地环境数据库连接"""
    return get_connection('local')


def get_online_connection():
    """获取线上环境数据库连接"""
    return get_connection('online')


def execute_query(sql, params=None, env: Optional[str] = None):
    """
    执行查询，返回字典列表

    Args:
        sql: SQL语句
        params: 参数
        env: 指定环境 'local' 或 'online'

    Returns:
        查询结果列表
    """
    conn = get_connection(env)
    cursor = conn.cursor(DictCursor)
    cursor.execute(sql, params or ())
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def execute_update(sql, params=None, env: Optional[str] = None):
    """
    执行单条更新/插入

    Args:
        sql: SQL语句
        params: 参数
        env: 指定环境

    Returns:
        影响行数
    """
    conn = get_connection(env)
    cursor = conn.cursor()
    cursor.execute(sql, params or ())
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected


def execute_many(sql, data_list, env: Optional[str] = None):
    """
    批量执行插入/更新

    Args:
        sql: SQL语句
        data_list: 数据列表
        env: 指定环境

    Returns:
        影响行数
    """
    conn = get_connection(env)
    cursor = conn.cursor()
    cursor.executemany(sql, data_list)
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected


def test_connection(env: Optional[str] = None):
    """
    测试数据库连接

    Args:
        env: 指定环境

    Returns:
        (是否成功, 消息)
    """
    try:
        conn = get_connection(env)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return True, "连接成功"
    except Exception as e:
        return False, str(e)


def get_current_env() -> str:
    """获取当前环境"""
    return CURRENT_ENV


def switch_env(env: str):
    """
    切换默认环境

    Args:
        env: 'local' 或 'online'
    """
    global CURRENT_ENV, DB_CONFIG
    if env not in ('local', 'online'):
        raise ValueError("env 必须是 'local' 或 'online'")
    CURRENT_ENV = env
    DB_CONFIG = LOCAL_DB_CONFIG if env == 'local' else ONLINE_DB_CONFIG


# ============================================================
# Dual-write primitives
# ============================================================

def get_dual_connections(primary_env=None, secondary_env=None):
    """
    Return (primary_conn, secondary_conn).

    secondary_conn may be None when dual-write is disabled or
    secondary_env is explicitly set to None.
    """
    if primary_env is None:
        primary_env = CURRENT_ENV
    conn = get_connection(primary_env)

    conn2 = None
    if secondary_env is not None:
        conn2 = get_connection(secondary_env)
    elif DUAL_WRITE:
        conn2 = get_connection(DUAL_WRITE_TARGET)

    return conn, conn2


def dual_executemany(conn, conn2, sql, rows, _logger=None, retries=1):
    """
    Execute executemany on primary, then best-effort with retry on secondary.

    Primary write must succeed. Secondary failure is logged but never raised.
    conn2 will be closed after this call (caller should NOT close it again).
    """
    # Primary write
    cursor = conn.cursor()
    cursor.executemany(sql, rows)
    conn.commit()
    cursor.close()

    # Secondary write (best-effort)
    if conn2:
        for attempt in range(1 + retries):
            try:
                cursor2 = conn2.cursor()
                cursor2.executemany(sql, rows)
                conn2.commit()
                cursor2.close()
                return
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                if _logger:
                    _logger.warning("Dual-write to %s failed after %d retries: %s",
                                    DUAL_WRITE_TARGET, retries + 1, e)
                try:
                    conn2.close()
                except Exception:
                    pass
                return
    if conn2:
        try:
            conn2.close()
        except Exception:
            pass


def dual_execute(conn, conn2, sql, params=None, _logger=None, retries=1):
    """
    Execute a single SQL on primary, then best-effort on secondary.

    Primary write must succeed. Secondary failure is logged but never raised.
    conn2 will be closed after this call (caller should NOT close it again).
    """
    # Primary write
    cursor = conn.cursor()
    cursor.execute(sql, params or ())
    conn.commit()
    affected = cursor.rowcount
    cursor.close()

    # Secondary write (best-effort)
    if conn2:
        for attempt in range(1 + retries):
            try:
                cursor2 = conn2.cursor()
                cursor2.execute(sql, params or ())
                conn2.commit()
                cursor2.close()
                return
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                if _logger:
                    _logger.warning("Dual-write to %s failed after %d retries: %s",
                                    DUAL_WRITE_TARGET, retries + 1, e)
                try:
                    conn2.close()
                except Exception:
                    pass
                return
    if conn2:
        try:
            conn2.close()
        except Exception:
            pass

    return affected


def execute_dual_update(sql, params=None, env=None, env2=None):
    """
    Execute single write on both envs. Failures on env2 are logged, not raised.

    Args:
        sql: SQL statement
        params: query parameters
        env: primary environment (default: CURRENT_ENV)
        env2: secondary environment (default: DUAL_WRITE_TARGET if DUAL_WRITE enabled)

    Returns:
        affected row count from primary
    """
    primary_env = env or CURRENT_ENV
    secondary_env = env2
    if secondary_env is None and DUAL_WRITE:
        secondary_env = DUAL_WRITE_TARGET

    affected = execute_update(sql, params, env=primary_env)

    if secondary_env:
        for attempt in range(2):  # 1 retry
            try:
                execute_update(sql, params, env=secondary_env)
                return affected
            except Exception as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                logger.warning("Dual-write execute_update to %s failed: %s", secondary_env, e)

    return affected


def execute_dual_many(sql, data_list, env=None, env2=None):
    """
    Execute batch write on both envs. Failures on env2 are logged, not raised.

    Args:
        sql: SQL statement
        data_list: list of parameter tuples
        env: primary environment (default: CURRENT_ENV)
        env2: secondary environment (default: DUAL_WRITE_TARGET if DUAL_WRITE enabled)

    Returns:
        affected row count from primary
    """
    primary_env = env or CURRENT_ENV
    secondary_env = env2
    if secondary_env is None and DUAL_WRITE:
        secondary_env = DUAL_WRITE_TARGET

    affected = execute_many(sql, data_list, env=primary_env)

    if secondary_env:
        for attempt in range(2):  # 1 retry
            try:
                execute_many(sql, data_list, env=secondary_env)
                return affected
            except Exception as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                logger.warning("Dual-write execute_many to %s failed: %s", secondary_env, e)

    return affected
