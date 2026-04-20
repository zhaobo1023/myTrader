# -*- coding: utf-8 -*-
"""牛熊三指标数据模型 + DDL"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

BULL_BEAR_SIGNAL_DDL = """
CREATE TABLE IF NOT EXISTS trade_bull_bear_signal (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    calc_date DATE NOT NULL,
    cn_10y_value DOUBLE,
    cn_10y_ma20 DOUBLE,
    cn_10y_trend VARCHAR(10) COMMENT 'UP/DOWN/FLAT',
    cn_10y_signal INT COMMENT '1=bullish, 0=neutral, -1=bearish',
    usdcny_value DOUBLE,
    usdcny_ma20 DOUBLE,
    usdcny_trend VARCHAR(10),
    usdcny_signal INT,
    dividend_relative DOUBLE COMMENT 'dividend/csi300 relative ratio',
    dividend_rel_ma20 DOUBLE,
    dividend_trend VARCHAR(10),
    dividend_signal INT,
    composite_score INT COMMENT 'sum of signals (-3 to +3)',
    regime VARCHAR(20) COMMENT 'BULL/BEAR/NEUTRAL',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_calc_date (calc_date),
    KEY idx_regime (regime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class BullBearSignal(BaseModel):
    calc_date: date
    cn_10y_value: Optional[float] = None
    cn_10y_ma20: Optional[float] = None
    cn_10y_trend: Optional[str] = None
    cn_10y_signal: int = 0
    usdcny_value: Optional[float] = None
    usdcny_ma20: Optional[float] = None
    usdcny_trend: Optional[str] = None
    usdcny_signal: int = 0
    dividend_relative: Optional[float] = None
    dividend_rel_ma20: Optional[float] = None
    dividend_trend: Optional[str] = None
    dividend_signal: int = 0
    composite_score: int = 0
    regime: str = 'NEUTRAL'
