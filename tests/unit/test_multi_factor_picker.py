# -*- coding: utf-8 -*-
"""
Unit tests for data_analyst.sw_rotation.multi_factor_picker pure functions.

No DB or network access required.
"""
import math
import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data_analyst.sw_rotation.multi_factor_picker import (
    rank_norm,
    calc_rsi,
    calc_bias_20,
    calc_composite_pick_score,
)


# ============================================================
# TestRankNorm
# ============================================================

class TestRankNorm:
    def test_basic_normalization(self):
        s = pd.Series([0.0, 50.0, 100.0])
        result = rank_norm(s)
        assert abs(result.iloc[0] - 0.0) < 1e-9
        assert abs(result.iloc[1] - 50.0) < 1e-9
        assert abs(result.iloc[2] - 100.0) < 1e-9

    def test_all_same_values(self):
        s = pd.Series([7.0, 7.0, 7.0, 7.0])
        result = rank_norm(s)
        assert all(abs(v - 50.0) < 1e-9 for v in result)

    def test_with_nan(self):
        s = pd.Series([10.0, np.nan, 20.0])
        result = rank_norm(s)
        assert abs(result.iloc[0] - 0.0) < 1e-9
        assert np.isnan(result.iloc[1])
        assert abs(result.iloc[2] - 100.0) < 1e-9

    def test_all_nan(self):
        s = pd.Series([np.nan, np.nan, np.nan])
        result = rank_norm(s)
        assert all(np.isnan(v) for v in result)


# ============================================================
# TestCalcRSI
# ============================================================

class TestCalcRSI:
    def test_rsi_range(self):
        np.random.seed(42)
        close = pd.Series(np.cumsum(np.random.randn(50)) + 100)
        rsi = calc_rsi(close, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_rsi_all_up(self):
        # Monotonically increasing -> RSI should be 100
        close = pd.Series([float(i) for i in range(1, 30)])
        rsi = calc_rsi(close, period=14)
        assert rsi is not None
        assert abs(rsi - 100.0) < 1e-6

    def test_rsi_insufficient_data(self):
        close = pd.Series([1.0, 2.0, 3.0])
        rsi = calc_rsi(close, period=14)
        assert rsi is None

    def test_rsi_stable_price(self):
        close = pd.Series([100.0] * 30)
        # All deltas are 0; no gains, no losses; RS = 0/0 edge case
        rsi = calc_rsi(close, period=14)
        # avg_loss == 0 -> return 100.0
        assert rsi == 100.0


# ============================================================
# TestCalcBias20
# ============================================================

class TestCalcBias20:
    def test_bias_above_ma(self):
        # Close above MA20 -> positive bias
        base = [100.0] * 20
        close = pd.Series(base[:-1] + [120.0])
        bias = calc_bias_20(close)
        assert bias is not None
        assert bias > 0

    def test_bias_below_ma(self):
        base = [100.0] * 20
        close = pd.Series(base[:-1] + [80.0])
        bias = calc_bias_20(close)
        assert bias is not None
        assert bias < 0

    def test_bias_at_ma(self):
        close = pd.Series([100.0] * 20)
        bias = calc_bias_20(close)
        assert bias is not None
        assert abs(bias) < 1e-6

    def test_bias_insufficient_data(self):
        close = pd.Series([100.0] * 10)
        bias = calc_bias_20(close)
        assert bias is None


# ============================================================
# TestCalcCompositePickScore
# ============================================================

class TestCalcCompositePickScore:
    def _make_df(self, n: int = 20, seed: int = 42) -> pd.DataFrame:
        np.random.seed(seed)
        return pd.DataFrame({
            'mom_1m': np.random.randn(n) * 5,
            'mom_3m': np.random.randn(n) * 10,
            'rev_5d': np.random.randn(n) * 2,
            'vol_20': np.abs(np.random.randn(n)) * 0.02 + 0.01,
            'rsi_14': np.random.uniform(20, 80, n),
            'bias_20': np.random.randn(n) * 3,
        })

    def test_score_range_0_to_100(self):
        df = self._make_df(50)
        scores = calc_composite_pick_score(df)
        valid = scores.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_direction_plus_minus(self):
        """(+) factors: high mom -> high score; (-) factors: low rsi -> high score."""
        # Create two extreme stocks:
        # Stock A: high mom_1m/mom_3m, low rev_5d/vol_20/rsi_14/bias_20 -> should rank best
        # Stock B: low mom, high reversal/vol/rsi/bias -> should rank worst
        n = 10
        base = pd.DataFrame({
            'mom_1m': np.zeros(n),
            'mom_3m': np.zeros(n),
            'rev_5d': np.zeros(n),
            'vol_20': np.ones(n) * 0.02,
            'rsi_14': np.ones(n) * 50.0,
            'bias_20': np.zeros(n),
        })

        base.loc[0, 'mom_1m'] = 100.0   # best mom_1m
        base.loc[0, 'mom_3m'] = 100.0   # best mom_3m
        base.loc[0, 'rsi_14'] = 0.0     # lowest RSI (overbought reversed)

        base.loc[1, 'mom_1m'] = -100.0  # worst mom_1m
        base.loc[1, 'mom_3m'] = -100.0  # worst mom_3m
        base.loc[1, 'rsi_14'] = 100.0   # highest RSI

        scores = calc_composite_pick_score(base)
        assert scores.iloc[0] > scores.iloc[1], (
            f"Best stock (score={scores.iloc[0]:.1f}) should beat worst (score={scores.iloc[1]:.1f})"
        )

    def test_rev_5d_direction(self):
        """
        rev_5d = -pct_change(5)，值越大表示近期跌幅越大。
        反转因子方向为 '+'：大 rev_5d → 高分（预期均值回归）。
        """
        n = 5
        df = pd.DataFrame({
            'rev_5d': [10.0, 5.0, 0.0, -5.0, -10.0],  # 降序：第0行跌最多
        })
        scores = calc_composite_pick_score(df)
        # 近期跌幅最大的股票（rev_5d=10）应得最高分
        assert scores.iloc[0] > scores.iloc[4], (
            f"高 rev_5d 应得高分: scores[0]={scores.iloc[0]:.1f}, scores[4]={scores.iloc[4]:.1f}"
        )

    def test_single_factor(self):
        """Only one factor column available; should still produce valid results."""
        df = pd.DataFrame({
            'mom_1m': [10.0, 5.0, 0.0, -5.0, -10.0],
        })
        scores = calc_composite_pick_score(df)
        assert scores.notna().all()
        assert (scores >= 0).all()
        assert (scores <= 100).all()

    def test_all_nan(self):
        """All NaN inputs -> NaN output."""
        df = pd.DataFrame({
            'mom_1m': [np.nan] * 5,
            'mom_3m': [np.nan] * 5,
            'rev_5d': [np.nan] * 5,
            'vol_20': [np.nan] * 5,
            'rsi_14': [np.nan] * 5,
            'bias_20': [np.nan] * 5,
        })
        scores = calc_composite_pick_score(df)
        # When all factors are NaN, each rank_norm returns NaN, mean of all-NaN is NaN
        assert scores.isna().all()

    def test_missing_columns(self):
        """If some factor columns are missing entirely, remainder still works."""
        df = pd.DataFrame({
            'mom_1m': [10.0, 5.0, 0.0],
            'mom_3m': [8.0, 4.0, 0.0],
            # rev_5d, vol_20, rsi_14, bias_20 all missing
        })
        scores = calc_composite_pick_score(df)
        # Should produce valid scores from available columns
        assert scores.notna().all()
