# -*- coding: utf-8 -*-
"""拥挤度数据模型 + DDL"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


CROWDING_SCORE_DDL = """
CREATE TABLE IF NOT EXISTS trade_crowding_score (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    calc_date DATE NOT NULL,
    dimension VARCHAR(30) NOT NULL COMMENT 'industry/style/overall',
    dimension_id VARCHAR(60) NOT NULL DEFAULT '',
    turnover_hhi DOUBLE COMMENT 'turnover HHI (0-1)',
    turnover_hhi_percentile DOUBLE COMMENT 'HHI 250d percentile',
    northbound_deviation DOUBLE COMMENT 'northbound flow deviation (sigma)',
    margin_concentration DOUBLE COMMENT 'margin trading concentration',
    svd_top1_ratio DOUBLE COMMENT 'SVD top1 variance ratio',
    crowding_score DOUBLE COMMENT 'composite score (0-100)',
    crowding_level VARCHAR(10) COMMENT 'LOW/MEDIUM/HIGH/CRITICAL',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_date_dim (calc_date, dimension, dimension_id),
    KEY idx_calc_date (calc_date),
    KEY idx_level (crowding_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class CrowdingScore(BaseModel):
    calc_date: date
    dimension: str = 'overall'
    dimension_id: str = ''
    turnover_hhi: Optional[float] = None
    turnover_hhi_percentile: Optional[float] = None
    northbound_deviation: Optional[float] = None
    margin_concentration: Optional[float] = None
    svd_top1_ratio: Optional[float] = None
    crowding_score: float = 0.0
    crowding_level: str = 'LOW'
