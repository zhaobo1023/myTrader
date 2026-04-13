# -*- coding: utf-8 -*-
"""
Tests for market dashboard calculator.

Uses mocking to avoid database dependency.
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from datetime import date, datetime


# ---------------------------------------------------------------------------
# Test helper functions
# ---------------------------------------------------------------------------

class TestSignalHelper:
    """Test the _signal threshold mapping function."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _signal
        self._signal = _signal

    def test_below_first_threshold(self):
        assert self._signal(5, [10, 20], ['low', 'mid', 'high']) == 'low'

    def test_between_thresholds(self):
        assert self._signal(15, [10, 20], ['low', 'mid', 'high']) == 'mid'

    def test_above_last_threshold(self):
        assert self._signal(25, [10, 20], ['low', 'mid', 'high']) == 'high'

    def test_exact_threshold_goes_to_next(self):
        # value == threshold is NOT < threshold, so it goes to next bucket
        assert self._signal(10, [10, 20], ['low', 'mid', 'high']) == 'mid'

    def test_negative_values(self):
        assert self._signal(-5, [-10, 0, 10], ['a', 'b', 'c', 'd']) == 'b'

    def test_single_threshold(self):
        assert self._signal(0.5, [1.0], ['below', 'above']) == 'below'
        assert self._signal(1.5, [1.0], ['below', 'above']) == 'above'


class TestSafeRound:
    """Test the _safe_round utility."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _safe_round
        self._safe_round = _safe_round

    def test_normal_value(self):
        assert self._safe_round(3.14159, 2) == 3.14

    def test_none(self):
        assert self._safe_round(None) is None

    def test_nan(self):
        assert self._safe_round(float('nan')) is None

    def test_integer(self):
        assert self._safe_round(5, 2) == 5.0

    def test_zero(self):
        assert self._safe_round(0.0, 2) == 0.0


class TestPctChangeStr:
    """Test percentage change string generation."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _pct_change_str
        self._pct_change_str = _pct_change_str

    def test_positive_change(self):
        result = self._pct_change_str(110, 100)
        assert result == '+10.0%'

    def test_negative_change(self):
        result = self._pct_change_str(90, 100)
        assert result == '-10.0%'

    def test_zero_prev(self):
        assert self._pct_change_str(100, 0) is None

    def test_none_values(self):
        assert self._pct_change_str(None, 100) is None
        assert self._pct_change_str(100, None) is None

    def test_no_change(self):
        result = self._pct_change_str(100, 100)
        assert result == '+0.0%'


# ---------------------------------------------------------------------------
# Test temperature score calculation
# ---------------------------------------------------------------------------

class TestTemperatureScore:
    """Test the composite temperature scoring logic."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _calc_temperature_score
        self._calc = _calc_temperature_score

    def test_neutral_baseline(self):
        """Empty indicators should give score near 50."""
        score = self._calc({})
        assert score == 50

    def test_all_hot_signals(self):
        """All indicators showing active/hot should give high score."""
        indicators = {
            'volume_ratio_ma20': {'value': 1.5},
            'turnover_pct_rank': {'value': 90},
            'advance_decline': {'ratio': 3.0},
            'margin_change_5d': {'value': 2.0},
        }
        score = self._calc(indicators)
        assert score > 70

    def test_all_cold_signals(self):
        """All indicators showing cold should give low score."""
        indicators = {
            'volume_ratio_ma20': {'value': 0.5},
            'turnover_pct_rank': {'value': 10},
            'advance_decline': {'ratio': 0.3},
            'margin_change_5d': {'value': -2.0},
        }
        score = self._calc(indicators)
        assert score < 30

    def test_score_clamped(self):
        """Score should always be between 0 and 100."""
        indicators = {
            'volume_ratio_ma20': {'value': 5.0},  # extreme
            'turnover_pct_rank': {'value': 100},
            'advance_decline': {'ratio': 10.0},
            'margin_change_5d': {'value': 10.0},
        }
        score = self._calc(indicators)
        assert 0 <= score <= 100

    def test_missing_indicator_values(self):
        """None values should be gracefully skipped."""
        indicators = {
            'volume_ratio_ma20': {'value': None},
            'turnover_pct_rank': {'value': 50},
        }
        score = self._calc(indicators)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# Test trend level calculation
# ---------------------------------------------------------------------------

class TestTrendLevel:
    """Test the composite trend level logic."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _calc_trend_level
        self._calc = _calc_trend_level

    def test_strong_bullish(self):
        data = {
            'indicators': {
                'ma_alignment': 'bullish',
                'ma_position': {'above': ['MA5', 'MA20', 'MA60', 'MA250'], 'below': []},
                'macd_weekly': {'status': 'golden_cross'},
                'adx': {'value': 30},
            },
            'indices': {
                'idx_csi300': {'change_pct': 2.0},
                'idx_sh': {'change_pct': 1.5},
            },
        }
        level = self._calc(data)
        assert level in ('strong_up', 'mild_up')

    def test_strong_bearish(self):
        data = {
            'indicators': {
                'ma_alignment': 'bearish',
                'ma_position': {'above': [], 'below': ['MA5', 'MA20', 'MA60', 'MA250']},
                'macd_weekly': {'status': 'dead_cross'},
                'adx': {'value': 30},
            },
            'indices': {
                'idx_csi300': {'change_pct': -2.0},
                'idx_sh': {'change_pct': -1.5},
            },
        }
        level = self._calc(data)
        assert level in ('panic_drop', 'weak_down')

    def test_consolidating(self):
        data = {
            'indicators': {
                'ma_alignment': 'tangled',
                'ma_position': {'above': ['MA5', 'MA20'], 'below': ['MA60', 'MA250']},
                'macd_weekly': {'status': 'above_zero'},
                'adx': {'value': 15},  # weak trend
            },
            'indices': {
                'idx_csi300': {'change_pct': 0.1},
            },
        }
        level = self._calc(data)
        assert level == 'consolidating'

    def test_empty_data(self):
        data = {'indicators': {}, 'indices': {}}
        level = self._calc(data)
        assert level == 'consolidating'


# ---------------------------------------------------------------------------
# Test fear-greed score calculation
# ---------------------------------------------------------------------------

class TestFearGreedScore:
    """Test the A-share local fear-greed composite score."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _calc_fear_greed_score
        self._calc = _calc_fear_greed_score

    def test_neutral_baseline(self):
        score = self._calc({})
        assert score == 50

    def test_fear_signals(self):
        indicators = {
            'qvix': {'value': 40},  # panic
            'north_flow': {'sum_5d': -50},  # big outflow
            'new_high_low': {'high': 10, 'low': 200},  # very bearish
            'seal_rate': {'value': 30},  # low seal
        }
        score = self._calc(indicators)
        assert score < 30

    def test_greed_signals(self):
        indicators = {
            'qvix': {'value': 12},  # very calm
            'north_flow': {'sum_5d': 50},  # big inflow
            'new_high_low': {'high': 200, 'low': 10},  # very bullish
            'seal_rate': {'value': 80},  # high seal
        }
        score = self._calc(indicators)
        assert score > 70

    def test_score_clamped(self):
        indicators = {
            'qvix': {'value': 5},
            'north_flow': {'sum_5d': 200},
            'margin_net_buy': {'sum_5d': 100},
            'new_high_low': {'high': 1000, 'low': 1},
            'seal_rate': {'value': 99},
        }
        score = self._calc(indicators)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# Test MACD weekly calculation
# ---------------------------------------------------------------------------

class TestWeeklyMACD:
    """Test the MACD weekly calculation."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _calc_weekly_macd
        self._calc = _calc_weekly_macd

    def test_insufficient_data(self):
        s = pd.Series([100.0] * 10, index=pd.date_range('2026-01-01', periods=10))
        result = self._calc(s)
        assert result['status'] == 'unknown'

    def test_uptrend_data(self):
        # 200 days of uptrending data
        dates = pd.date_range('2025-01-01', periods=200, freq='B')
        values = [100 + i * 0.5 for i in range(200)]
        s = pd.Series(values, index=dates)
        result = self._calc(s)
        assert result['status'] in ('golden_cross', 'above_zero')
        assert result['dif'] is not None

    def test_downtrend_data(self):
        dates = pd.date_range('2025-01-01', periods=200, freq='B')
        values = [200 - i * 0.5 for i in range(200)]
        s = pd.Series(values, index=dates)
        result = self._calc(s)
        assert result['status'] in ('dead_cross', 'below_zero')


# ---------------------------------------------------------------------------
# Test ADX calculation
# ---------------------------------------------------------------------------

class TestADX:
    """Test the simplified ADX calculation."""

    def setup_method(self):
        from data_analyst.market_dashboard.calculator import _calc_adx
        self._calc = _calc_adx

    def test_insufficient_data(self):
        s = pd.Series([100.0] * 10, index=pd.date_range('2026-01-01', periods=10))
        result = self._calc(s)
        assert result['value'] is None
        assert result['signal'] == 'unknown'

    def test_trending_data(self):
        dates = pd.date_range('2025-01-01', periods=100, freq='B')
        values = [100 + i * 2 for i in range(100)]
        s = pd.Series(values, index=dates)
        result = self._calc(s)
        assert result['value'] is not None
        assert result['value'] >= 0

    def test_flat_data(self):
        dates = pd.date_range('2025-01-01', periods=100, freq='B')
        values = [100.0] * 100
        s = pd.Series(values, index=dates)
        result = self._calc(s)
        # Flat data should show low ADX or unknown
        if result['value'] is not None:
            assert result['signal'] in ('consolidating', 'unknown')


# ---------------------------------------------------------------------------
# Test with mocked database
# ---------------------------------------------------------------------------

class TestComputeDashboardMocked:
    """Test compute_dashboard with mocked database calls."""

    @patch('data_analyst.market_dashboard.calculator.execute_query')
    @patch('data_analyst.market_dashboard.calculator._load_macro')
    def test_all_empty_data(self, mock_load, mock_query):
        """Dashboard should still return a valid structure with no data."""
        mock_load.return_value = pd.Series(dtype=float)
        mock_query.return_value = []

        # Also mock the imported market_overview functions
        with patch('data_analyst.market_overview.calculator.calc_market_turnover', return_value={'available': False}), \
             patch('data_analyst.market_overview.calculator.calc_scale_rotation', return_value={'available': False}), \
             patch('data_analyst.market_overview.calculator.calc_style_rotation', return_value={'available': False}), \
             patch('data_analyst.market_overview.calculator.calc_anchor_5y', return_value={'available': False}), \
             patch('data_analyst.market_overview.calculator.calc_stock_bond_spread', return_value={'available': False}), \
             patch('data_analyst.market_overview.calculator.calc_dividend_tracking', return_value={'available': False}), \
             patch('data_analyst.market_overview.calculator.calc_equity_fund_rolling', return_value={'available': False}), \
             patch('data_analyst.market_overview.calculator.calc_macro_pulse', return_value={'available': False}):

            from data_analyst.market_dashboard.calculator import compute_dashboard
            result = compute_dashboard()

        # Verify structure
        assert 'updated_at' in result
        assert 'temperature' in result
        assert 'trend' in result
        assert 'sentiment' in result
        assert 'style' in result
        assert 'stock_bond' in result
        assert 'macro' in result
        assert 'signal_log' in result

        # Each section should have 'available' key
        for section in ['temperature', 'trend', 'sentiment']:
            assert 'available' in result[section], f"Missing 'available' in {section}"
