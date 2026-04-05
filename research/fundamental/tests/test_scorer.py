# -*- coding: utf-8 -*-
import pytest
from research.fundamental.scorer import FundamentalScorer, ScorerInput, ScoreResult


def _inp(**kwargs):
    defaults = dict(
        pe_quantile=0.30, pb_quantile=0.25, fcf_yield=0.05,
        roe=0.18, roe_prev=0.15, ocf_to_profit=1.1,
        debt_ratio=0.45, revenue_yoy=0.15, profit_yoy=0.20,
    )
    defaults.update(kwargs)
    return ScorerInput(**defaults)


def test_composite_within_0_100():
    s = FundamentalScorer().score(_inp())
    assert 0 <= s.composite_score <= 100


def test_low_pe_quantile_high_valuation():
    s = FundamentalScorer().score(_inp(pe_quantile=0.05))
    assert s.valuation_score >= 30


def test_high_pe_quantile_low_valuation():
    s = FundamentalScorer().score(_inp(pe_quantile=0.90, pb_quantile=0.85))
    assert s.valuation_score <= 10


def test_high_roe_improving_high_earnings():
    s = FundamentalScorer().score(_inp(roe=0.28, roe_prev=0.22, ocf_to_profit=1.3))
    assert s.earnings_quality_score >= 35


def test_label_youzhi_for_high_score():
    s = FundamentalScorer().score(_inp(
        pe_quantile=0.05, pb_quantile=0.05, fcf_yield=0.10,
        roe=0.30, roe_prev=0.25, ocf_to_profit=1.5,
        revenue_yoy=0.35, profit_yoy=0.40,
    ))
    assert s.label in ('优质', '良好')


def test_label_ruoishi_for_low_score():
    s = FundamentalScorer().score(_inp(
        pe_quantile=0.95, pb_quantile=0.90, fcf_yield=0.01,
        roe=0.03, roe_prev=0.06, ocf_to_profit=0.3,
        debt_ratio=0.80, revenue_yoy=-0.10, profit_yoy=-0.15,
    ))
    assert s.label in ('偏弱', '较差')


def test_none_inputs_dont_crash():
    s = FundamentalScorer().score(ScorerInput())
    assert 0 <= s.composite_score <= 100
