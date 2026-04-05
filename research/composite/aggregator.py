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


@dataclass
class AggregateResult:
    composite_score: int
    direction: str
    signal_note: str
    scores: FiveSectionScores


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
        1. Apply cross-section override rules.
        2. Boost fundamental score if applicable.
        3. Compute weighted composite.
        4. Clamp to [0, 100].
        5. Determine direction (override or threshold-based).
        6. Return AggregateResult.
        """
        rule = apply_rules(
            phase=s.capital_cycle_phase,
            fundamental_score=s.score_fundamental,
            pe_quantile=s.pe_quantile,
            sentiment_score=s.score_sentiment,
            founder_reducing=s.founder_reducing,
            technical_breakdown=s.technical_breakdown,
        )

        boosted_fund = min(100.0, s.score_fundamental * rule.fundamental_weight_boost)

        raw = (
            s.score_technical * W_TECHNICAL
            + s.score_fund_flow * W_FUND_FLOW
            + boosted_fund * W_FUNDAMENTAL
            + s.score_sentiment * W_SENTIMENT
            + s.score_capital_cycle * W_CAPITAL_CYCLE
        )

        composite = int(max(0, min(100, raw)))

        direction = (
            rule.override_direction
            if rule.override_direction is not None
            else _score_to_direction(composite)
        )

        return AggregateResult(
            composite_score=composite,
            direction=direction,
            signal_note=rule.signal_note,
            scores=s,
        )
