# -*- coding: utf-8 -*-
"""tests for signal detector"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta


class TestSignalDetector:

    def test_breakout_signal(self):
        """log_bias crosses above 5 -> breakout"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': 4.0, 'signal_state': 'normal',
                'last_breakout_date': None, 'last_stall_date': None}
        curr = {'log_bias': 6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'breakout'

    def test_pullback_signal(self):
        """after breakout, log_bias falls to [0,5) -> pullback"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': 7.0, 'signal_state': 'breakout',
                'last_breakout_date': date.today() - timedelta(days=5),
                'last_stall_date': None}
        curr = {'log_bias': 3.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'pullback'

    def test_stall_signal(self):
        """log_bias < -5 -> stall"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': -3.0, 'signal_state': 'normal',
                'last_breakout_date': None, 'last_stall_date': None}
        curr = {'log_bias': -6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'stall'

    def test_overheat_signal(self):
        """log_bias > 15 -> overheat"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': 12.0, 'signal_state': 'breakout',
                'last_breakout_date': date.today(), 'last_stall_date': None}
        curr = {'log_bias': 16.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'overheat'

    def test_cooldown_period(self):
        """within 10 days of stall, no breakout allowed"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector(cooldown_days=10)
        prev = {'log_bias': 4.0, 'signal_state': 'normal',
                'last_breakout_date': None,
                'last_stall_date': date.today() - timedelta(days=5)}
        curr = {'log_bias': 6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] != 'breakout'
        assert result['signal_state'] == 'normal'

    def test_cooldown_expired(self):
        """after cooldown expires, breakout is allowed again"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector(cooldown_days=10)
        prev = {'log_bias': 4.0, 'signal_state': 'normal',
                'last_breakout_date': None,
                'last_stall_date': date.today() - timedelta(days=15)}
        curr = {'log_bias': 6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'breakout'

    def test_detect_all(self):
        """detect_all produces signal_state column"""
        from strategist.log_bias.calculator import calculate_log_bias
        from strategist.log_bias.signal_detector import SignalDetector
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(200) * 0.5)
        df = pd.DataFrame({'close': prices})
        result = calculate_log_bias(df)
        detector = SignalDetector()
        signals = detector.detect_all(result)
        assert 'signal_state' in signals.columns
        assert len(signals) == len(result)
