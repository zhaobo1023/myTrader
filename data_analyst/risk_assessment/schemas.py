# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from data_analyst.risk_assessment.config import RISK_LEVELS


def score_to_level(score: float) -> str:
    """根据 RISK_LEVELS 将风险分转为 LOW/MEDIUM/HIGH/CRITICAL。"""
    for low, high, level in RISK_LEVELS:
        if low <= score < high:
            return level
    # score == 100 时归入 CRITICAL
    return 'CRITICAL'


@dataclass
class RiskScore:
    score: float
    level: str
    details: Dict
    suggestions: List[str]


@dataclass
class MacroRiskResult(RiskScore):
    suggested_max_exposure: float = 1.0


@dataclass
class RegimeRiskResult(RiskScore):
    market_state: str = ''
    avg_correlation: float = 0.0
    high_corr_pairs: List[Tuple[str, str, float]] = field(default_factory=list)


@dataclass
class SectorRiskResult(RiskScore):
    industry_breakdown: Dict[str, float] = field(default_factory=dict)
    overvalued_industries: List[str] = field(default_factory=list)


@dataclass
class StockRiskResult:
    stock_code: str
    stock_name: str
    score: float
    sub_scores: Dict[str, float]
    alerts: List[str]
    stop_loss_hit: bool


@dataclass
class DataStatus:
    name: str
    latest_date: str
    delay_days: int
    status: str


@dataclass
class LayeredRiskResult:
    scan_time: str
    user_id: int
    data_status: List[DataStatus]
    macro: MacroRiskResult
    regime: RegimeRiskResult
    sector: SectorRiskResult
    stocks: List[StockRiskResult]
    overall_score: float
    overall_suggestions: List[str]
