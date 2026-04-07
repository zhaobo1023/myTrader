# -*- coding: utf-8 -*-
"""
Weighted 5-section composite scoring aggregator.

Combines technical, fund-flow, fundamental, sentiment, and capital-cycle
section scores into a single composite score, then applies cross-section
override rules to determine trade direction.
"""
from __future__ import annotations

from dataclasses import dataclass

from research.composite.rules import apply_rules

# --- Section weights (must sum to 1.0) ---
W_TECHNICAL = 0.15
W_FUND_FLOW = 0.20
W_FUNDAMENTAL = 0.30
W_SENTIMENT = 0.15
W_CAPITAL_CYCLE = 0.20


@dataclass
class FiveSectionScores:
    score_technical: int = 50
    score_fund_flow: int = 50
    score_fundamental: int = 50
    score_sentiment: int = 50
    score_capital_cycle: int = 50
    pe_quantile: float = 0.5
    capital_cycle_phase: int = 0
    founder_reducing: bool = False
    technical_breakdown: bool = False
    # v2
    industry_type: object = None    # IndustryType enum
    pb_quantile: float = 0.5
    # 各截面权重调整系数（来自 HealthChecker）
    weight_adjustments: dict = None


@dataclass
class AggregateResult:
    composite_score: int
    direction: str
    signal_note: str
    scores: FiveSectionScores
    # v2: 双维度
    quality_score: int = 0      # 资产质地 = 基本面 60% + 周期 40%
    timing_score: int = 0       # 交易择时 = 技术 40% + 资金 35% + 情绪 25%
    quality_label: str = ""
    timing_label: str = ""
    suggestion: str = ""
    rule_triggered: str = ""


def _score_to_direction(score: int) -> str:
    """Convert a numeric composite score to a direction label."""
    if score >= 75:
        return 'strong_bull'
    if score >= 60:
        return 'bull'
    if score >= 45:
        return 'neutral'
    if score >= 30:
        return 'bear'
    return 'strong_bear'


class CompositeAggregator:
    """Aggregate five-section scores into a composite result."""

    def aggregate(self, s: FiveSectionScores) -> AggregateResult:
        """Compute composite score and determine trade direction.

        Steps
        -----
        1. Apply weight adjustments from health checker.
        2. Apply cross-section override rules (industry-aware).
        3. Boost fundamental score if applicable.
        4. Compute weighted composite (renormalize if weights adjusted).
        5. Compute dual-dimension scores (quality + timing).
        6. Determine direction (override or threshold-based).
        7. Return AggregateResult.
        """
        # Step 1: weight adjustments from health checker
        adj = s.weight_adjustments or {}
        w_tech = W_TECHNICAL * adj.get("technical", 1.0)
        w_ff = W_FUND_FLOW * adj.get("fund_flow", 1.0)
        w_fund = W_FUNDAMENTAL * adj.get("fundamental", 1.0)
        w_sent = W_SENTIMENT * adj.get("sentiment", 1.0)
        w_cc = W_CAPITAL_CYCLE * adj.get("capital_cycle", 1.0)

        # 归一化权重（避免数据缺失导致总分偏低）
        total_w = w_tech + w_ff + w_fund + w_sent + w_cc
        if total_w > 0:
            w_tech /= total_w
            w_ff /= total_w
            w_fund /= total_w
            w_sent /= total_w
            w_cc /= total_w

        # Step 2: cross-section rules (v2: industry-aware)
        rule = apply_rules(
            phase=s.capital_cycle_phase,
            fundamental_score=s.score_fundamental,
            pe_quantile=s.pe_quantile,
            sentiment_score=s.score_sentiment,
            founder_reducing=s.founder_reducing,
            technical_breakdown=s.technical_breakdown,
            industry_type=s.industry_type,
            pb_quantile=s.pb_quantile,
        )

        # Step 3: boost
        boosted_fund = min(100.0, s.score_fundamental * rule.fundamental_weight_boost)

        # Step 4: composite
        raw = (
            s.score_technical * w_tech
            + s.score_fund_flow * w_ff
            + boosted_fund * w_fund
            + s.score_sentiment * w_sent
            + s.score_capital_cycle * w_cc
        )
        composite = int(max(0, min(100, raw)))

        direction = (
            rule.override_direction
            if rule.override_direction is not None
            else _score_to_direction(composite)
        )

        # Step 5: v2 dual-dimension scores
        quality_score = int(s.score_fundamental * 0.6 + s.score_capital_cycle * 0.4)
        timing_score = int(
            s.score_technical * 0.40
            + s.score_fund_flow * 0.35
            + s.score_sentiment * 0.25
        )
        quality_label = _quality_label(quality_score)
        timing_label = _timing_label(timing_score)
        suggestion = _generate_suggestion(quality_score, timing_score)

        return AggregateResult(
            composite_score=composite,
            direction=direction,
            signal_note=rule.signal_note,
            scores=s,
            quality_score=quality_score,
            timing_score=timing_score,
            quality_label=quality_label,
            timing_label=timing_label,
            suggestion=suggestion,
            rule_triggered=rule.rule_triggered,
        )


def _quality_label(score: int) -> str:
    if score >= 75:
        return "优质资产"
    if score >= 60:
        return "质地良好"
    if score >= 45:
        return "质地一般"
    return "质地较差"


def _timing_label(score: int) -> str:
    if score >= 65:
        return "择时偏多"
    if score >= 50:
        return "企稳观望"
    if score >= 35:
        return "短期回调"
    return "择时偏空"


def _generate_suggestion(quality: int, timing: int) -> str:
    """根据双维度生成简洁的操作建议。"""
    if quality >= 70 and timing >= 60:
        return "优质资产择时偏多，可考虑加仓"
    if quality >= 70 and timing < 45:
        return "优质资产短期回调，关注支撑位企稳后左侧建仓"
    if quality >= 70 and timing < 60:
        return "优质资产短期震荡，持仓观望，等待择时信号"
    if quality >= 55 and timing >= 55:
        return "质地良好且短线偏多，可小仓参与"
    if quality < 50 and timing >= 60:
        return "质地一般但短线强势，谨慎追高，控制仓位"
    if quality < 50 and timing < 45:
        return "质地一般且短线偏空，建议减仓或回避"
    return "维持现有仓位，等待信号明确"
