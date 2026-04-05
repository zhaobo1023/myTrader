# -*- coding: utf-8 -*-
import pytest
from research.composite.aggregator import CompositeAggregator, FiveSectionScores, AggregateResult
from research.composite.rules import apply_rules, RuleResult


def _scores(**kwargs):
    defaults = dict(score_technical=60, score_fund_flow=55,
                    score_fundamental=70, score_sentiment=50,
                    score_capital_cycle=65, pe_quantile=0.35,
                    capital_cycle_phase=3, founder_reducing=False,
                    technical_breakdown=False)
    defaults.update(kwargs)
    return FiveSectionScores(**defaults)


# --- rules tests ---

def test_phase4_high_pe_overrides_strong_bear():
    r = apply_rules(phase=4, fundamental_score=80, pe_quantile=0.85,
                    sentiment_score=60, founder_reducing=False,
                    technical_breakdown=False)
    assert r.override_direction == 'strong_bear'


def test_founder_reducing_and_breakdown_overrides_bear():
    r = apply_rules(phase=1, fundamental_score=80, pe_quantile=0.30,
                    sentiment_score=60, founder_reducing=True,
                    technical_breakdown=True)
    assert r.override_direction == 'bear'


def test_phase3_high_fundamental_boosts():
    r = apply_rules(phase=3, fundamental_score=75, pe_quantile=0.30,
                    sentiment_score=60, founder_reducing=False,
                    technical_breakdown=False)
    assert r.fundamental_weight_boost == pytest.approx(1.3)
    assert r.override_direction is None


def test_phase2_low_sentiment_wait_note():
    r = apply_rules(phase=2, fundamental_score=60, pe_quantile=0.30,
                    sentiment_score=40, founder_reducing=False,
                    technical_breakdown=False)
    assert '等待' in r.signal_note
    assert r.override_direction is None


def test_phase4_rule_takes_priority_over_boost():
    # Even if fundamental is high, phase4+high_pe overrides immediately
    r = apply_rules(phase=4, fundamental_score=90, pe_quantile=0.90,
                    sentiment_score=70, founder_reducing=False,
                    technical_breakdown=False)
    assert r.override_direction == 'strong_bear'
    assert r.fundamental_weight_boost == 1.0   # no boost applied


# --- aggregator tests ---

def test_all_100_gives_100():
    s = _scores(score_technical=100, score_fund_flow=100,
                score_fundamental=100, score_sentiment=100,
                score_capital_cycle=100, capital_cycle_phase=0)
    r = CompositeAggregator().aggregate(s)
    assert r.composite_score == 100


def test_phase4_high_pe_overrides_direction():
    s = _scores(capital_cycle_phase=4, pe_quantile=0.90,
                score_fundamental=85)
    r = CompositeAggregator().aggregate(s)
    assert r.direction == 'strong_bear'


def test_direction_bull_for_high_scores():
    s = _scores(score_technical=80, score_fund_flow=75,
                score_fundamental=85, score_sentiment=70,
                score_capital_cycle=80, capital_cycle_phase=0)
    r = CompositeAggregator().aggregate(s)
    assert r.direction in ('strong_bull', 'bull')


def test_composite_within_bounds():
    s = _scores()
    r = CompositeAggregator().aggregate(s)
    assert 0 <= r.composite_score <= 100
