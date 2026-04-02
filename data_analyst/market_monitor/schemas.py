# -*- coding: utf-8 -*-
"""
SVD 市场监控数据模型 + DDL 定义
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


# ============================================================
# DDL
# ============================================================

SVD_MARKET_STATE_DDL = """
CREATE TABLE IF NOT EXISTS trade_svd_market_state (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    calc_date DATE NOT NULL COMMENT '计算日期',
    window_size INT NOT NULL COMMENT '窗口大小',
    universe_type VARCHAR(20) NOT NULL DEFAULT '全A' COMMENT '股票池类型: 全A/SW_L1',
    universe_id VARCHAR(40) NOT NULL DEFAULT '' COMMENT '股票池ID: 行业名(申万一级行业)',
    top1_var_ratio DOUBLE COMMENT 'Factor1 方差占比',
    top3_var_ratio DOUBLE COMMENT 'Top3 方差占比',
    top5_var_ratio DOUBLE COMMENT 'Top5 方差占比',
    reconstruction_error DOUBLE COMMENT '前5因子重构误差',
    market_state VARCHAR(20) COMMENT '市场状态',
    stock_count INT COMMENT '有效股票数',
    is_mutation TINYINT DEFAULT 0 COMMENT '是否突变警报',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_date_window_universe (calc_date, window_size, universe_type, universe_id),
    KEY idx_calc_date (calc_date),
    KEY idx_universe (universe_type, universe_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


# ============================================================
# Pydantic Models
# ============================================================

class WindowSVDResult(BaseModel):
    """单个窗口的 SVD 结果"""
    calc_date: date
    window_size: int
    universe_type: str = "全A"
    universe_id: str = ""
    top1_var_ratio: float
    top3_var_ratio: float
    top5_var_ratio: float
    reconstruction_error: float
    stock_count: int


class MarketRegime(BaseModel):
    """市场状态判定结果"""
    calc_date: date
    market_state: str = Field(description="齐涨齐跌 / 板块分化 / 个股行情")
    is_mutation: bool = False
    final_score: float
    f1_short: Optional[float] = None
    f1_mid: Optional[float] = None
    f1_long: Optional[float] = None
    weights_used: dict = {}


class SVDRecord(WindowSVDResult):
    """数据库记录模型 (继承窗口结果 + 增加状态字段)"""
    market_state: str = ""
    is_mutation: int = 0
