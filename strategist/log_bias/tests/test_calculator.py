# -*- coding: utf-8 -*-
"""tests for log bias calculator"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
import pandas as pd
import numpy as np


class TestLogBiasCalculator:

    def test_log_bias_basic(self):
        """basic correctness: log_bias sign matches price direction"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [10.0, 10.5, 11.0, 10.8, 11.2]})
        result = calculate_log_bias(df)
        assert np.isclose(result['ln_close'].iloc[0], np.log(10.0))
        assert result['log_bias'].iloc[-1] > 0

    def test_log_bias_ema_convergence(self):
        """EMA convergence: after 120 days of constant price, log_bias ~ 0"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [100.0] * 200})
        result = calculate_log_bias(df)
        assert abs(result['log_bias'].iloc[120]) < 0.01
        assert abs(result['log_bias'].iloc[-1]) < 0.001

    def test_log_bias_nan_handling(self):
        """NaN should propagate"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [10.0, np.nan, 11.0, 10.5]})
        result = calculate_log_bias(df)
        assert pd.isna(result['ln_close'].iloc[1])

    def test_log_bias_low_price(self):
        """low price (<1 yuan) should not error"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [0.5, 0.52, 0.48, 0.51, 0.50]})
        result = calculate_log_bias(df)
        assert not result['log_bias'].isna().all()

    def test_output_columns(self):
        """output should have exact columns"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [10.0] * 30})
        result = calculate_log_bias(df)
        expected_cols = ['close', 'ln_close', 'ema_ln', 'log_bias']
        assert list(result.columns) == expected_cols
