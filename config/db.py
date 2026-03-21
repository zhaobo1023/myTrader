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
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
from typing import Optional

# 加载 .env 文件
load_dotenv()

# 当前环境: 'local' 或 'online'
CURRENT_ENV = os.getenv('DB_ENV', 'local')


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
