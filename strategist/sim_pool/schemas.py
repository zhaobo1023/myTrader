# -*- coding: utf-8 -*-
"""DDL definitions and ensure_tables() for sim_pool system."""

import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config.db import execute_update

logger = logging.getLogger('myTrader.sim_pool')

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SIM_POOL_DDL = """
CREATE TABLE IF NOT EXISTS sim_pool (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id     INT NOT NULL COMMENT 'ref strategies.id',
    name            VARCHAR(100) NOT NULL COMMENT 'e.g. momentum_20260414',
    strategy_type   VARCHAR(30) NOT NULL COMMENT 'momentum|industry|micro_cap|custom',
    signal_date     DATE NOT NULL COMMENT 'screening date',
    entry_date      DATE COMMENT 'T+1 actual buy date',
    initial_cash    DOUBLE NOT NULL DEFAULT 1000000,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    COMMENT 'pending|active|closed',
    stock_count     INT COMMENT 'number of positions',
    total_return    DOUBLE COMMENT 'cumulative return',
    benchmark_code  VARCHAR(20) DEFAULT '000300.SH',
    benchmark_return DOUBLE COMMENT 'benchmark cumulative return',
    max_drawdown    DOUBLE,
    sharpe_ratio    DOUBLE,
    win_rate        DOUBLE,
    params          TEXT COMMENT 'JSON: SimPoolConfig fields',
    user_id         INT COMMENT 'owner user id',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at       DATETIME,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_strategy (strategy_id),
    INDEX idx_status (status),
    INDEX idx_signal_date (signal_date),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='strategy sim pool'
"""

_SIM_POSITION_DDL = """
CREATE TABLE IF NOT EXISTS sim_position (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    pool_id         INT NOT NULL,
    stock_code      VARCHAR(20) NOT NULL,
    stock_name      VARCHAR(50),
    weight          DOUBLE NOT NULL COMMENT 'position weight, equal=1/N',
    shares          INT COMMENT 'number of shares (multiple of 100)',
    entry_price     DOUBLE COMMENT 'T+1 actual buy price (close)',
    entry_date      DATE,
    entry_cost      DOUBLE COMMENT 'total cost including commission+slippage',
    current_price   DOUBLE COMMENT 'latest close price',
    exit_price      DOUBLE COMMENT 'exit execution price',
    exit_date       DATE,
    exit_reason     VARCHAR(20) COMMENT 'stop_loss|take_profit|max_hold|strategy',
    gross_return    DOUBLE COMMENT 'gross return rate',
    net_return      DOUBLE COMMENT 'net return after costs',
    suspended_days  INT NOT NULL DEFAULT 0 COMMENT 'consecutive suspended days',
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    COMMENT 'pending|active|exited',
    signal_meta     TEXT COMMENT 'JSON: rps/score/industry etc from screener',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pool (pool_id),
    INDEX idx_stock (stock_code),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='sim pool position detail'
"""

_SIM_DAILY_NAV_DDL = """
CREATE TABLE IF NOT EXISTS sim_daily_nav (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    pool_id          INT NOT NULL,
    nav_date         DATE NOT NULL,
    portfolio_value  DOUBLE COMMENT 'total position market value',
    cash             DOUBLE COMMENT 'remaining cash',
    total_value      DOUBLE COMMENT 'portfolio_value + cash',
    nav              DOUBLE COMMENT 'unit NAV, initial=1.0',
    daily_return     DOUBLE COMMENT 'daily return rate',
    benchmark_close  DOUBLE COMMENT 'benchmark index close',
    benchmark_nav    DOUBLE COMMENT 'benchmark unit NAV',
    drawdown         DOUBLE COMMENT 'drawdown from historical peak',
    active_positions INT COMMENT 'active position count on this day',
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pool_date (pool_id, nav_date),
    INDEX idx_pool (pool_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='daily NAV snapshot'
"""

_SIM_TRADE_LOG_DDL = """
CREATE TABLE IF NOT EXISTS sim_trade_log (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    pool_id     INT NOT NULL,
    position_id INT NOT NULL,
    stock_code  VARCHAR(20) NOT NULL,
    trade_date  DATE NOT NULL,
    action      VARCHAR(10) NOT NULL COMMENT 'buy|sell',
    price       DOUBLE NOT NULL COMMENT 'execution price (after slippage)',
    shares      INT NOT NULL,
    amount      DOUBLE COMMENT 'gross trade amount',
    commission  DOUBLE COMMENT 'commission fee',
    slippage_cost DOUBLE COMMENT 'slippage cost',
    stamp_tax   DOUBLE COMMENT 'stamp duty (sell only)',
    net_amount  DOUBLE COMMENT 'actual cash change (negative=outflow)',
    `trigger`   VARCHAR(20) COMMENT 'entry|stop_loss|take_profit|max_hold|strategy',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pool (pool_id),
    INDEX idx_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='trade audit log'
"""

_SIM_REPORT_DDL = """
CREATE TABLE IF NOT EXISTS sim_report (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    pool_id     INT NOT NULL,
    report_date DATE NOT NULL,
    report_type VARCHAR(20) NOT NULL COMMENT 'daily|weekly|final',
    metrics     TEXT COMMENT 'JSON: full BacktestResult compatible metrics',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pool_date_type (pool_id, report_date, report_type),
    INDEX idx_pool (pool_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='performance report snapshot'
"""

ALL_DDL = [
    _SIM_POOL_DDL,
    _SIM_POSITION_DDL,
    _SIM_DAILY_NAV_DDL,
    _SIM_TRADE_LOG_DDL,
    _SIM_REPORT_DDL,
]


def ensure_tables(env: str = 'online') -> None:
    """Create all sim_pool tables if they do not exist."""
    from config.db import get_connection
    conn = get_connection(env=env)
    try:
        cursor = conn.cursor()
        for ddl in ALL_DDL:
            cursor.execute(ddl)
        conn.commit()
        cursor.close()
        logger.info('[sim_pool] ensure_tables ok (env=%s)', env)
    finally:
        conn.close()
