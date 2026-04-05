# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch
from research.sentiment.scorer import SentimentScorer, SentimentInput, SentimentResult


def _inp(**kwargs):
    defaults = dict(rsi=50.0, macd_hist=0.0, vol_ratio=1.0, rps_120=50.0,
                    score_fund=50, score_consensus=50, score_macro=50)
    defaults.update(kwargs)
    return SentimentInput(**defaults)


def test_composite_within_bounds():
    r = SentimentScorer().score(_inp())
    assert 0 <= r.composite_score <= 100


def test_oversold_rsi_gives_higher_pricevol():
    s = SentimentScorer()
    oversold = s._price_vol_score(_inp(rsi=25.0, macd_hist=-0.1))
    overbought = s._price_vol_score(_inp(rsi=75.0, macd_hist=0.5))
    assert oversold > overbought


def test_neutral_inputs_give_mid_score():
    r = SentimentScorer().score(_inp())
    assert 40 <= r.composite_score <= 65


def test_label_qiangduo_for_high_score():
    r = SentimentScorer().score(_inp(
        rsi=28.0, macd_hist=-0.1, vol_ratio=0.4,
        rps_120=90.0, score_fund=90, score_consensus=85, score_macro=80
    ))
    assert r.label in ('强多', '中性偏多')


def test_label_qiangkong_for_low_score():
    r = SentimentScorer().score(_inp(
        rsi=82.0, macd_hist=0.9, vol_ratio=2.5,
        rps_120=5.0, score_fund=10, score_consensus=15, score_macro=20
    ))
    assert r.label in ('强空', '中性偏空')


def test_historical_quantile_none_insufficient():
    scorer = SentimentScorer()
    with patch('research.sentiment.scorer.execute_query',
               return_value=[{'cnt': 10}]):
        q = scorer._compute_historical_quantile('300750', 60)
    assert q is None


def test_historical_quantile_computed_when_enough():
    scorer = SentimentScorer()
    with patch('research.sentiment.scorer.execute_query',
               side_effect=[[{'cnt': 80}], [{'pct': 0.72}]]):
        q = scorer._compute_historical_quantile('300750', 60)
    assert q == pytest.approx(0.72)


def test_none_inputs_dont_crash():
    r = SentimentScorer().score(SentimentInput())
    assert 0 <= r.composite_score <= 100
