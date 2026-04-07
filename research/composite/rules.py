# -*- coding: utf-8 -*-
"""
Cross-section override rules for composite scoring.

Rules are applied in priority order. Higher-priority rules return early
and prevent lower-priority rules from being evaluated.

v2 变更：
- apply_rules 新增 industry_type / pb_quantile 参数
- PRIORITY 1 泡沫期规则区分行业类型：
    周期资源：Phase 3/4 + PB 分位 > 75% -> 周期景气见顶警告
    其他行业：Phase 4 + PE 分位 > 80% -> 原有逻辑
  原因：周期股在 Phase 4 时 PE 往往很低（利润还在高位），
  等 PE 分位 > 80% 触发时股价可能早已腰斩。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuleResult:
    override_direction: str | None = None   # if set, overrides computed direction
    fundamental_weight_boost: float = 1.0   # multiplier on fundamental score
    signal_note: str = ''
    rule_triggered: str = ''                # v2: 触发的规则名称


def apply_rules(
    phase: int,
    fundamental_score: float,
    pe_quantile: float,
    sentiment_score: float,
    founder_reducing: bool,
    technical_breakdown: bool,
    industry_type: object = None,           # v2: IndustryType enum
    pb_quantile: float = 0.5,              # v2: PB 历史分位
) -> RuleResult:
    """Apply cross-section override rules and return a RuleResult.

    Rules are evaluated in descending priority order. Rules marked
    'return immediately' short-circuit the evaluation chain.

    Parameters
    ----------
    phase:               Capital-cycle phase (1-5).
    fundamental_score:   Raw fundamental score (0-100).
    pe_quantile:         PE percentile versus 5yr history (0-1).
    sentiment_score:     Market sentiment score (0-100).
    founder_reducing:    Whether the founder is reducing holdings.
    technical_breakdown: Whether price has broken below key support.
    industry_type:       IndustryType enum (v2).
    pb_quantile:         PB percentile versus 5yr history (0-1) (v2).

    Returns
    -------
    RuleResult with optional override_direction, weight boost, and note.
    """
    result = RuleResult()

    # 延迟导入避免循环依赖
    is_cyclical = False
    try:
        from research.industry_classifier import IndustryType
        is_cyclical = (industry_type == IndustryType.CYCLICAL)
    except ImportError:
        pass

    # PRIORITY 1 — 泡沫期检测（行业类型感知）
    if is_cyclical:
        # 周期股：不用 PE 分位，用 PB 分位 + 资本周期阶段
        # Phase 3/4（景气高点/供给放量）+ PB 历史高位 -> 警告
        if phase in (3, 4) and pb_quantile > 0.75:
            result.override_direction = 'bear'
            result.signal_note = (
                f'[周期股] 景气阶段 Phase {phase} + PB 分位 {pb_quantile:.0%}，'
                f'警惕周期见顶，不追高'
            )
            result.rule_triggered = 'P1_CYCLICAL_BUBBLE'
            return result
    else:
        # 成长/消费/金融：原有 PE 分位逻辑
        if phase == 4 and pe_quantile > 0.80:
            result.override_direction = 'strong_bear'
            result.signal_note = '资本周期阶段4 + 估值历史高位，坚决不追'
            result.rule_triggered = 'P1_GROWTH_BUBBLE'
            return result

    # PRIORITY 2 — founder dumping shares AND technical breakdown
    if founder_reducing and technical_breakdown:
        result.override_direction = 'bear'
        result.signal_note = '创始人减持 + 技术面破位，降仓警戒'
        result.rule_triggered = 'P2_REDUCE_BREAKDOWN'
        return result

    # BOOST — phase 3 expansion with strong fundamentals (no early return)
    if phase == 3 and fundamental_score > 70:
        result.fundamental_weight_boost = 1.3
        result.signal_note = '资本周期阶段3 + 基本面高分，强买'
        result.rule_triggered = 'BOOST_PHASE3'

    # WAIT — phase 2 with depressed sentiment (no early return)
    elif phase == 2 and sentiment_score < 45:
        result.signal_note = '资本周期阶段2 + 情绪低迷，等待催化布局'
        result.rule_triggered = 'WAIT_PHASE2'

    return result
