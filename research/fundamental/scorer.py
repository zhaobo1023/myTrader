# -*- coding: utf-8 -*-
"""
research/fundamental/scorer.py

Pure scoring engine for fundamental analysis.
No DB calls. Takes a ScorerInput dataclass and returns a ScoreResult.

Scoring formula:
    composite (0-100) = earnings_quality (0-40) + valuation_attractiveness (0-40) + growth_certainty (0-20)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScorerInput:
    """All inputs are optional; missing (None) values are skipped in scoring."""
    pe_quantile: float | None = None      # 0..1  (current PE position in 5yr history)
    pb_quantile: float | None = None      # 0..1
    fcf_yield: float | None = None        # e.g. 0.05 = 5%
    roe: float | None = None              # e.g. 0.18 = 18%
    roe_prev: float | None = None         # previous year ROE for trend
    ocf_to_profit: float | None = None    # OCF / net profit ratio
    debt_ratio: float | None = None       # total_liab / total_assets
    revenue_yoy: float | None = None      # e.g. 0.15 = 15% growth
    profit_yoy: float | None = None


@dataclass
class ScoreResult:
    earnings_quality_score: int    # 0..40
    valuation_score: int           # 0..40
    growth_score: int              # 0..20
    composite_score: int           # 0..100
    label: str                     # human-readable quality label


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _label(composite: int) -> str:
    if composite >= 85:
        return "优质"
    if composite >= 70:
        return "良好"
    if composite >= 55:
        return "中性"
    if composite >= 40:
        return "一般"
    if composite >= 25:
        return "偏弱"
    return "较差"


class FundamentalScorer:
    """
    Stateless scoring engine.

    Usage:
        scorer = FundamentalScorer()
        result = scorer.score(ScorerInput(roe=0.20, pe_quantile=0.30, ...))
    """

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def score(self, inp: ScorerInput) -> ScoreResult:
        eq = self._earnings_quality(inp)
        va = self._valuation(inp)
        gc = self._growth_certainty(inp)
        composite = eq + va + gc
        return ScoreResult(
            earnings_quality_score=eq,
            valuation_score=va,
            growth_score=gc,
            composite_score=composite,
            label=_label(composite),
        )

    # -----------------------------------------------------------------
    # Sub-scorers
    # -----------------------------------------------------------------

    def _earnings_quality(self, inp: ScorerInput) -> int:
        """
        0-40, neutral start = 20.

        ROE level:
            >= 25% -> +15
            >= 20% -> +10
            >= 15% -> +5
            <   5% -> -10

        ROE trend (vs roe_prev):
            improving -> +5
            declining > 3ppt -> -5

        OCF/profit:
            >= 1.2 -> +10
            >= 0.8 -> +5
            <  0.5 -> -10

        Leverage:
            debt_ratio > 0.70 -> -5
        """
        pts = 20

        # ROE level
        if inp.roe is not None:
            if inp.roe >= 0.25:
                pts += 15
            elif inp.roe >= 0.20:
                pts += 10
            elif inp.roe >= 0.15:
                pts += 5
            elif inp.roe < 0.05:
                pts -= 10

        # ROE trend
        if inp.roe is not None and inp.roe_prev is not None:
            if inp.roe > inp.roe_prev:
                pts += 5
            elif inp.roe_prev - inp.roe > 0.03:
                pts -= 5

        # OCF/profit ratio
        if inp.ocf_to_profit is not None:
            if inp.ocf_to_profit >= 1.2:
                pts += 10
            elif inp.ocf_to_profit >= 0.8:
                pts += 5
            elif inp.ocf_to_profit < 0.5:
                pts -= 10

        # Leverage
        if inp.debt_ratio is not None and inp.debt_ratio > 0.70:
            pts -= 5

        return _clamp(pts, 0, 40)

    def _valuation(self, inp: ScorerInput) -> int:
        """
        0-40, start = 0.

        PE quantile:
            score += round(25 - 35 * pe_quantile)
            e.g. 0.0 -> +25, 0.5 -> +7, 1.0 -> -10

        PB quantile:
            score += round(10 - 15 * pb_quantile)
            e.g. 0.0 -> +10, 0.5 -> +2, 1.0 -> -5

        FCF yield:
            >= 8% -> +5
            >= 5% -> +2
        """
        pts = 0

        if inp.pe_quantile is not None:
            pts += round(25 - 35 * inp.pe_quantile)

        if inp.pb_quantile is not None:
            pts += round(10 - 15 * inp.pb_quantile)

        if inp.fcf_yield is not None:
            if inp.fcf_yield >= 0.08:
                pts += 5
            elif inp.fcf_yield >= 0.05:
                pts += 2

        return _clamp(pts, 0, 40)

    def _growth_certainty(self, inp: ScorerInput) -> int:
        """
        0-20, neutral start = 10.

        revenue_yoy:
            >= 30% -> +6
            >= 15% -> +3
            <   0% -> -5

        profit_yoy:
            >= 30% -> +4
            >= 15% -> +2
            <   0% -> -4
        """
        pts = 10

        if inp.revenue_yoy is not None:
            if inp.revenue_yoy >= 0.30:
                pts += 6
            elif inp.revenue_yoy >= 0.15:
                pts += 3
            elif inp.revenue_yoy < 0.0:
                pts -= 5

        if inp.profit_yoy is not None:
            if inp.profit_yoy >= 0.30:
                pts += 4
            elif inp.profit_yoy >= 0.15:
                pts += 2
            elif inp.profit_yoy < 0.0:
                pts -= 4

        return _clamp(pts, 0, 20)
