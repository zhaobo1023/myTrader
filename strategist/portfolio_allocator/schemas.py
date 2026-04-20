# -*- coding: utf-8 -*-
"""策略权重数据模型 + DDL"""
from pydantic import BaseModel
from typing import Optional
from datetime import date


STRATEGY_WEIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS trade_strategy_weights (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    calc_date DATE NOT NULL,
    strategy_name VARCHAR(50) NOT NULL,
    base_weight DOUBLE,
    regime_adjustment DOUBLE,
    crowding_adjustment DOUBLE,
    final_weight DOUBLE,
    regime VARCHAR(20),
    crowding_level VARCHAR(10),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_date_strategy (calc_date, strategy_name),
    KEY idx_calc_date (calc_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class StrategyWeight(BaseModel):
    calc_date: date
    strategy_name: str
    base_weight: float
    regime_adjustment: float = 0.0
    crowding_adjustment: float = 0.0
    final_weight: float
    regime: Optional[str] = None
    crowding_level: Optional[str] = None
