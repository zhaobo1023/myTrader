# -*- coding: utf-8 -*-
"""
Cross-section override rules for composite scoring.

Rules are applied in priority order. Higher-priority rules return early
and prevent lower-priority rules from being evaluated.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuleResult:
    override_direction: str | None = None   # if set, overrides computed direction
    fundamental_weight_boost: float = 1.0   # multiplier on fundamental score
    signal_note: str = ''


def apply_rules(
    phase: int,
    fundamental_score: float,
    pe_quantile: float,
    sentiment_score: float,
    founder_reducing: bool,
    technical_breakdown: bool,
) -> RuleResult:
    """Apply cross-section override rules and return a RuleResult.

    Rules are evaluated in descending priority order. Rules marked
    'return immediately' short-circuit the evaluation chain.

    Parameters
    ----------
    phase:               Capital-cycle phase (1-4).
    fundamental_score:   Raw fundamental score (0-100).
    pe_quantile:         PE percentile versus history (0-1).
    sentiment_score:     Market sentiment score (0-100).
    founder_reducing:    Whether the founder is reducing holdings.
    technical_breakdown: Whether price has broken below key support.

    Returns
    -------
    RuleResult with optional override_direction, weight boost, and note.
    """
    result = RuleResult()

    # PRIORITY 1 — phase 4 AND historically expensive valuation
    if phase == 4 and pe_quantile > 0.80:
        result.override_direction = 'strong_bear'
        result.signal_note = '资本周期阶段4 + 估值历史高位，坚决不追'
        return result

    # PRIORITY 2 — founder dumping shares AND technical breakdown
    if founder_reducing and technical_breakdown:
        result.override_direction = 'bear'
        result.signal_note = '创始人减持 + 技术面破位，降仓警戒'
        return result

    # BOOST — phase 3 expansion with strong fundamentals (no early return)
    if phase == 3 and fundamental_score > 70:
        result.fundamental_weight_boost = 1.3
        result.signal_note = '资本周期阶段3 + 基本面高分，强买'

    # WAIT — phase 2 with depressed sentiment (no early return)
    elif phase == 2 and sentiment_score < 45:
        result.signal_note = '资本周期阶段2 + 情绪低迷，等待催化布局'

    return result
