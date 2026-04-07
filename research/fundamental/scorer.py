# -*- coding: utf-8 -*-
"""
research/fundamental/scorer.py

Pure scoring engine for fundamental analysis.
No DB calls. Takes a ScorerInput dataclass and returns a ScoreResult.

Scoring formula:
    composite (0-100) = earnings_quality (0-40) + valuation_attractiveness (0-40) + growth_certainty (0-20)

v2 变更：
- ScorerInput 新增 industry_type 字段
- _valuation 根据行业类型分流：
    周期资源 -> PB-ROE 模型（不用 PE 分位）
    金融地产 -> PB 主导
    成长/消费/未知 -> 原 PE 分位逻辑
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research.industry_classifier import IndustryType


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
    # v2: 行业类型，影响估值评分逻辑
    industry_type: object = None          # IndustryType enum，None 时走默认 PE 逻辑


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
        0-40，根据行业类型选择不同的估值模型：

        周期资源（CYCLICAL）：PB-ROE 模型
            周期股"高 PE 买，低 PE 卖"，PE 分位在景气高点反而偏低，不可用。
            改用：高 ROE + 低 PB 分位 = 景气期估值合理 = 高分

        金融地产（FINANCIAL）：PB 主导
            金融股 PE 波动大，PB 更稳定。

        成长/消费/未知：原 PE 分位主导逻辑
            低 PE 分位 = 低估 = 高分
        """
        industry_type = inp.industry_type

        # 延迟导入避免循环依赖
        try:
            from research.industry_classifier import IndustryType
            is_cyclical = (industry_type == IndustryType.CYCLICAL)
            is_financial = (industry_type == IndustryType.FINANCIAL)
        except ImportError:
            is_cyclical = False
            is_financial = False

        if is_cyclical:
            return self._valuation_cyclical(inp)
        if is_financial:
            return self._valuation_financial(inp)
        return self._valuation_growth(inp)

    def _valuation_cyclical(self, inp: ScorerInput) -> int:
        """
        周期资源股估值：PB-ROE 模型，0-40 分。

        ROE >= 15%（景气期）+ PB 分位 < 40% -> 买点，最高分
        ROE >= 15%（景气期）+ PB 分位 >= 40% -> 估值偏贵，中分
        ROE <  15%（低谷期）+ PB 分位 < 40% -> 可能见底，中高分
        ROE <  15%（低谷期）+ PB 分位 >= 40% -> 估值陷阱，低分
        """
        roe = inp.roe or 0.0
        pb_q = inp.pb_quantile if inp.pb_quantile is not None else 0.5

        is_boom = roe >= 0.15
        is_cheap = pb_q < 0.40

        if is_boom and is_cheap:
            base = 32
        elif is_boom and not is_cheap:
            base = 16
        elif not is_boom and is_cheap:
            base = 22
        else:
            base = 6

        # FCF yield 附加分（与行业无关）
        if inp.fcf_yield is not None:
            if inp.fcf_yield >= 0.08:
                base += 5
            elif inp.fcf_yield >= 0.05:
                base += 2

        return _clamp(base, 0, 40)

    def _valuation_financial(self, inp: ScorerInput) -> int:
        """
        金融地产股估值：PB 主导，0-40 分。
        """
        pts = 0
        if inp.pb_quantile is not None:
            # PB 权重更大：0-35 分
            pts += round(20 - 30 * inp.pb_quantile)
        if inp.pe_quantile is not None:
            # PE 仅作参考：0-5 分
            pts += round(5 - 7 * inp.pe_quantile)
        return _clamp(pts, 0, 40)

    def _valuation_growth(self, inp: ScorerInput) -> int:
        """
        成长/消费/默认：PE 分位主导，0-40 分。
        原有逻辑保持不变。
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
