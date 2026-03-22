# -*- coding: utf-8 -*-
"""
配置文件 - 从 .env 读取数据库连接和回测参数

支持双环境：
  - LOCAL_* : 本地开发环境
  - ONLINE_* : 线上生产环境（从原 quant 项目迁移）

默认环境由 DB_ENV 控制，默认为 'local'
"""
from pathlib import Path
from dotenv import dotenv_values
import os

_env_path = Path(__file__).parent.parent / '.env'
_env = dotenv_values(_env_path)

# 当前环境
CURRENT_ENV = os.getenv('DB_ENV', _env.get('DB_ENV', 'local'))


def _get_db_config(prefix: str) -> dict:
    """根据前缀获取数据库配置"""
    return {
        'host': _env.get(f'{prefix}_DB_HOST', 'localhost'),
        'user': _env.get(f'{prefix}_DB_USER', 'root'),
        'password': _env.get(f'{prefix}_DB_PASSWORD', ''),
        'database': _env.get(f'{prefix}_DB_NAME', 'mytrader'),
        'port': int(_env.get(f'{prefix}_DB_PORT', '3306')),
        'charset': 'utf8mb4'
    }


# 本地数据库配置
LOCAL_DB_CONFIG = _get_db_config('LOCAL')

# 线上数据库配置（从 quant 项目迁移）
ONLINE_DB_CONFIG = _get_db_config('ONLINE')

# 当前使用的数据库配置
DB_CONFIG = LOCAL_DB_CONFIG if CURRENT_ENV == 'local' else ONLINE_DB_CONFIG


# ============================================================
# 回测参数（可在 .env 中修改）
# ============================================================
INITIAL_CASH = int(_env.get('BACKTEST_INITIAL_CASH', '1000000'))
COMMISSION = float(_env.get('BACKTEST_COMMISSION', '0.0002'))
POSITION_PCT = int(_env.get('BACKTEST_POSITION_PCT', '95'))


# ============================================================
# QMT配置
# ============================================================
QMT_DATA_PATH = _env.get('QMT_DATA_PATH', '')


# ============================================================
# Tushare配置
# ============================================================
TUSHARE_TOKEN = _env.get('TUSHARE_TOKEN', '')

# ============================================================
# 騡拟推送服务（用于测试）
# ============================================================
MOCK_PUSH_SERVICE = _env.get('MOCK_PUSH_SERVICE', 'True').lower() == 'true'

FEISHU_WEBHOOK_URL = _env.get('FEISHU_WEBHOOK_URL', '')


# ============================================================
# 风控参数
# ============================================================
MAX_POSITION_PCT = float(_env.get('MAX_POSITION_PCT', '0.3'))  # 单只股票最大仓位
MAX_SINGLE_LOSS_PCT = float(_env.get('MAX_SINGLE_LOSS_PCT', '0.05'))  # 单笔最大亏损
DEFAULT_STOP_LOSS_PCT = float(_env.get('DEFAULT_STOP_LOSS_PCT', '0.08'))  # 默认止损比例
DEFAULT_TAKE_PROFIT_PCT = float(_env.get('DEFAULT_TAKE_PROFIT_PCT', '0.15'))  # 默认止盈比例
