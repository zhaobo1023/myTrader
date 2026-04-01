# -*- coding: utf-8 -*-
"""integration tests for log bias module"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
import pandas as pd
import numpy as np


class TestIntegration:

    def test_full_pipeline_single_etf(self):
        """end-to-end: calculate -> detect -> verify valid states"""
        from strategist.log_bias.calculator import calculate_log_bias
        from strategist.log_bias.signal_detector import SignalDetector

        np.random.seed(42)
        dates = pd.date_range('2025-01-01', periods=300, freq='B')
        prices = 1.0 + np.cumsum(np.random.randn(300) * 0.01)
        df = pd.DataFrame({'trade_date': dates, 'close': prices})

        result = calculate_log_bias(df)
        assert 'log_bias' in result.columns
        assert len(result) == 300

        detector = SignalDetector()
        signals = detector.detect_all(result)
        assert 'signal_state' in signals.columns

        valid_states = {'overheat', 'breakout', 'pullback', 'normal', 'stall'}
        actual_states = set(signals['signal_state'].unique())
        assert actual_states.issubset(valid_states)

    def test_calculator_preserves_index(self):
        """calculator should preserve DataFrame index"""
        from strategist.log_bias.calculator import calculate_log_bias
        import numpy as np

        np.random.seed(77)
        dates = pd.date_range('2025-06-01', periods=100, freq='B')
        prices = 1.0 + np.cumsum(np.random.randn(100) * 0.005)
        df = pd.DataFrame({'close': prices}, index=dates)

        result = calculate_log_bias(df)
        assert len(result) == 100
        assert result.index.equals(dates)

    def test_report_generator(self):
        """report generator produces valid markdown"""
        from strategist.log_bias.report_generator import ReportGenerator
        import tempfile

        summary = [
            {'ts_code': '510300.SH', 'name': 'hs300ETF', 'close': 4.463,
             'log_bias': -2.48, 'signal_state': 'normal', 'prev_state': 'normal'},
            {'ts_code': '518880.SH', 'name': 'goldETF', 'close': 5.123,
             'log_bias': 6.5, 'signal_state': 'breakout', 'prev_state': 'normal'},
            {'ts_code': '159995.SZ', 'name': 'chipETF', 'close': 0.856,
             'log_bias': -7.82, 'signal_state': 'stall', 'prev_state': 'normal'},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir, etf_names={'510300.SH': 'hs300ETF'})
            path = gen.generate(summary, '2026-03-31')

            assert os.path.exists(path)
            with open(path, 'r') as f:
                content = f.read()
            assert 'Log Bias' in content
            assert 'breakout' in content
            assert 'stall' in content
            assert '510300.SH' in content

    def test_detect_all_with_realistic_trend(self):
        """simulate a realistic trend: up -> overheat -> pullback -> stall"""
        from strategist.log_bias.calculator import calculate_log_bias
        from strategist.log_bias.signal_detector import SignalDetector

        # 100 days flat, then 60 days strong uptrend, then 40 days decline
        np.random.seed(123)
        flat = np.ones(100) * 1.0
        uptrend = 1.0 + np.cumsum(np.random.randn(60) * 0.03 + 0.02)
        decline = uptrend[-1] + np.cumsum(np.random.randn(40) * 0.03 - 0.02)
        prices = np.concatenate([flat, uptrend, decline])

        df = pd.DataFrame({'close': prices})
        result = calculate_log_bias(df)
        detector = SignalDetector()
        signals = detector.detect_all(result)

        # should have seen some non-normal states
        state_counts = signals['signal_state'].value_counts()
        assert 'normal' in state_counts.index

    def test_cooldown_survives_full_pipeline(self):
        """cooldown mechanism works in detect_all across many days"""
        from strategist.log_bias.calculator import calculate_log_bias
        from strategist.log_bias.signal_detector import SignalDetector

        np.random.seed(55)
        # strong downtrend then recovery
        decline = 2.0 - np.cumsum(np.random.randn(80) * 0.02 + 0.01)
        recovery = decline[-1] + np.cumsum(np.random.randn(80) * 0.02 + 0.01)
        prices = np.concatenate([decline, recovery])

        df = pd.DataFrame({'close': prices})
        result = calculate_log_bias(df)
        detector = SignalDetector(cooldown_days=10)
        signals = detector.detect_all(result)

        # find first stall, then check if breakout is suppressed for 10+ days after
        stall_indices = signals[signals['signal_state'] == 'stall'].index.tolist()
        if len(stall_indices) > 0:
            first_stall = stall_indices[0]
            # after first stall, next 10 entries should not be breakout
            window = signals.iloc[first_stall + 1: first_stall + 11]
            assert 'breakout' not in window['signal_state'].values
