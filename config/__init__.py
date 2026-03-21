# -*- coding: utf-8 -*-
"""
配置模块

支持双环境数据库配置：
  - LOCAL_* : 本地开发环境
  - ONLINE_* : 线上生产环境
"""
from .db import (
    get_connection,
    get_local_connection,
    get_online_connection,
    execute_query,
    execute_update,
    execute_many,
    test_connection,
    get_current_env,
    switch_env,
    DB_CONFIG,
    LOCAL_DB_CONFIG,
    ONLINE_DB_CONFIG,
    CURRENT_ENV,
)
from .settings import (
    DB_CONFIG,
    LOCAL_DB_CONFIG,
    ONLINE_DB_CONFIG,
    CURRENT_ENV,
    INITIAL_CASH,
    COMMISSION,
    POSITION_PCT,
    QMT_DATA_PATH,
    TUSHARE_TOKEN,
    MAX_POSITION_PCT,
    MAX_SINGLE_LOSS_PCT,
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
)
