# -*- coding: utf-8 -*-
"""
Unit tests for data_analyst/bull_bear_monitor/ module.

Pure-Python tests: no DB, no network.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date


# ---------------------------------------------------------------------------
# Test BullBearConfig
# ---------------------------------------------------------------------------

class TestBullBearConfig:
    def test_default_values(self):
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        cfg = BullBearConfig()
        assert cfg.ma_short == 20
        assert cfg.ma_long == 60
        assert cfg.bond_bull_threshold == 2.5
        assert cfg.bond_bear_threshold == 3.0
        assert cfg.bull_threshold == 2
        assert cfg.bear_threshold == -2

    def test_custom_values(self):
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        cfg = BullBearConfig(ma_short=10, bond_bull_threshold=2.0)
        assert cfg.ma_short == 10
        assert cfg.bond_bull_threshold == 2.0


# ---------------------------------------------------------------------------
# Test BullBearSignal schema
# ---------------------------------------------------------------------------

class TestBullBearSignal:
    def test_create_signal(self):
        from data_analyst.bull_bear_monitor.schemas import BullBearSignal
        s = BullBearSignal(
            calc_date=date(2026, 4, 20),
            cn_10y_signal=1,
            usdcny_signal=1,
            dividend_signal=-1,
            composite_score=1,
            regime='NEUTRAL',
        )
        assert s.calc_date == date(2026, 4, 20)
        assert s.composite_score == 1
        assert s.regime == 'NEUTRAL'

    def test_default_values(self):
        from data_analyst.bull_bear_monitor.schemas import BullBearSignal
        s = BullBearSignal(calc_date=date(2026, 1, 1))
        assert s.cn_10y_signal == 0
        assert s.usdcny_signal == 0
        assert s.dividend_signal == 0
        assert s.composite_score == 0
        assert s.regime == 'NEUTRAL'
        assert s.cn_10y_value is None

    def test_ddl_string_exists(self):
        from data_analyst.bull_bear_monitor.schemas import BULL_BEAR_SIGNAL_DDL
        assert 'trade_bull_bear_signal' in BULL_BEAR_SIGNAL_DDL
        assert 'composite_score' in BULL_BEAR_SIGNAL_DDL
        assert 'uk_calc_date' in BULL_BEAR_SIGNAL_DDL


# ---------------------------------------------------------------------------
# Test IndicatorEngine
# ---------------------------------------------------------------------------

def _make_series(values, start='2025-01-01'):
    """Helper: create a DataFrame with date index and 'value' column."""
    dates = pd.date_range(start=start, periods=len(values), freq='B')
    return pd.DataFrame({'value': values}, index=dates)


class TestIndicatorEngineBond:
    def test_bullish_signal(self):
        """MA20 < MA60 and value < 2.5% => signal = +1"""
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine

        cfg = BullBearConfig(ma_short=5, ma_long=10)
        engine = IndicatorEngine(cfg)

        # Build a declining bond yield series (MA5 < MA10, values < 2.5)
        values = list(np.linspace(2.8, 2.0, 20))
        df = _make_series(values)
        result = engine.compute_bond_signal(df)

        assert not result.empty
        last = result.iloc[-1]
        assert last['cn_10y_trend'] == 'DOWN'
        assert last['cn_10y_signal'] == 1  # bullish

    def test_bearish_signal(self):
        """MA20 > MA60 and value > 3.0% => signal = -1"""
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine

        cfg = BullBearConfig(ma_short=5, ma_long=10)
        engine = IndicatorEngine(cfg)

        # Build a rising bond yield series (MA5 > MA10, values > 3.0)
        values = list(np.linspace(2.5, 3.5, 20))
        df = _make_series(values)
        result = engine.compute_bond_signal(df)

        last = result.iloc[-1]
        assert last['cn_10y_trend'] == 'UP'
        assert last['cn_10y_signal'] == -1  # bearish

    def test_neutral_signal(self):
        """Value between thresholds => signal = 0"""
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine

        cfg = BullBearConfig(ma_short=5, ma_long=10)
        engine = IndicatorEngine(cfg)

        # Flat around 2.7 (between 2.5 and 3.0)
        values = [2.7] * 20
        df = _make_series(values)
        result = engine.compute_bond_signal(df)

        last = result.iloc[-1]
        assert last['cn_10y_signal'] == 0  # neutral

    def test_empty_input(self):
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine
        engine = IndicatorEngine()
        result = engine.compute_bond_signal(pd.DataFrame())
        assert result.empty


class TestIndicatorEngineUSDCNY:
    def test_bullish_rmb_appreciating(self):
        """MA20 < MA60 (RMB appreciating) => signal = +1"""
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine

        cfg = BullBearConfig(ma_short=5, ma_long=10)
        engine = IndicatorEngine(cfg)

        # Declining USDCNY = RMB appreciating
        values = list(np.linspace(7.3, 7.0, 30))
        df = _make_series(values)
        result = engine.compute_usdcny_signal(df)

        last = result.iloc[-1]
        assert last['usdcny_trend'] == 'DOWN'
        assert last['usdcny_signal'] == 1

    def test_bearish_rmb_depreciating_with_momentum(self):
        """MA20 > MA60 and 20d rise > 1% => signal = -1"""
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine

        cfg = BullBearConfig(ma_short=5, ma_long=10, usdcny_rise_pct=0.01)
        engine = IndicatorEngine(cfg)

        # Sharply rising USDCNY
        values = list(np.linspace(7.0, 7.3, 30))
        df = _make_series(values)
        result = engine.compute_usdcny_signal(df)

        last = result.iloc[-1]
        assert last['usdcny_trend'] == 'UP'
        assert last['usdcny_signal'] == -1

    def test_empty_input(self):
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine
        engine = IndicatorEngine()
        result = engine.compute_usdcny_signal(pd.DataFrame())
        assert result.empty


class TestIndicatorEngineDividend:
    def test_bullish_dividend_underperforming(self):
        """Dividend/CSI300 ratio declining (risk-on) => signal = +1"""
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine

        cfg = BullBearConfig(ma_short=5, ma_long=10)
        engine = IndicatorEngine(cfg)

        dates = pd.date_range('2025-01-01', periods=30, freq='B')
        # Dividend flat, CSI300 rising => ratio declining
        dividend_df = pd.DataFrame({'value': [5000.0] * 30}, index=dates)
        csi300_df = pd.DataFrame({'value': np.linspace(3000, 4000, 30)}, index=dates)

        result = engine.compute_dividend_signal(dividend_df, csi300_df)
        last = result.iloc[-1]
        assert last['dividend_trend'] == 'DOWN'
        assert last['dividend_signal'] == 1  # risk-on = bullish

    def test_bearish_dividend_outperforming(self):
        """Dividend/CSI300 ratio rising (risk-off) => signal = -1"""
        from data_analyst.bull_bear_monitor.config import BullBearConfig
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine

        cfg = BullBearConfig(ma_short=5, ma_long=10)
        engine = IndicatorEngine(cfg)

        dates = pd.date_range('2025-01-01', periods=30, freq='B')
        # Dividend rising, CSI300 flat => ratio rising
        dividend_df = pd.DataFrame({'value': np.linspace(4000, 6000, 30)}, index=dates)
        csi300_df = pd.DataFrame({'value': [3500.0] * 30}, index=dates)

        result = engine.compute_dividend_signal(dividend_df, csi300_df)
        last = result.iloc[-1]
        assert last['dividend_trend'] == 'UP'
        assert last['dividend_signal'] == -1  # risk-off = bearish

    def test_empty_input(self):
        from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine
        engine = IndicatorEngine()
        result = engine.compute_dividend_signal(pd.DataFrame(), pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# Test RegimeJudge
# ---------------------------------------------------------------------------

class TestRegimeJudge:
    def _make_signal_dfs(self, bond_signals, usdcny_signals, dividend_signals):
        """Helper to create signal DataFrames for regime judgment."""
        dates = pd.date_range('2025-06-01', periods=len(bond_signals), freq='B')

        bond_df = pd.DataFrame({
            'cn_10y_value': [2.3] * len(bond_signals),
            'cn_10y_ma20': [2.4] * len(bond_signals),
            'cn_10y_trend': ['DOWN'] * len(bond_signals),
            'cn_10y_signal': bond_signals,
        }, index=dates)

        usdcny_df = pd.DataFrame({
            'usdcny_value': [7.1] * len(usdcny_signals),
            'usdcny_ma20': [7.15] * len(usdcny_signals),
            'usdcny_trend': ['DOWN'] * len(usdcny_signals),
            'usdcny_signal': usdcny_signals,
        }, index=dates)

        dividend_df = pd.DataFrame({
            'dividend_relative': [1.5] * len(dividend_signals),
            'dividend_rel_ma20': [1.55] * len(dividend_signals),
            'dividend_trend': ['DOWN'] * len(dividend_signals),
            'dividend_signal': dividend_signals,
        }, index=dates)

        return bond_df, usdcny_df, dividend_df

    def test_bull_regime(self):
        from data_analyst.bull_bear_monitor.regime_judge import RegimeJudge
        judge = RegimeJudge()

        bond_df, usdcny_df, div_df = self._make_signal_dfs(
            [1, 1, 1], [1, 1, 1], [1, 1, 0]
        )
        signals = judge.judge(bond_df, usdcny_df, div_df)
        assert len(signals) == 3
        # First two: 1+1+1=3 >= 2 => BULL
        assert signals[0].regime == 'BULL'
        assert signals[0].composite_score == 3
        # Last: 1+1+0=2 >= 2 => BULL
        assert signals[2].regime == 'BULL'
        assert signals[2].composite_score == 2

    def test_bear_regime(self):
        from data_analyst.bull_bear_monitor.regime_judge import RegimeJudge
        judge = RegimeJudge()

        bond_df, usdcny_df, div_df = self._make_signal_dfs(
            [-1, -1, -1], [-1, -1, -1], [-1, 0, -1]
        )
        signals = judge.judge(bond_df, usdcny_df, div_df)
        assert signals[0].regime == 'BEAR'
        assert signals[0].composite_score == -3
        # Second: -1 + -1 + 0 = -2 => BEAR
        assert signals[1].regime == 'BEAR'
        assert signals[1].composite_score == -2

    def test_neutral_regime(self):
        from data_analyst.bull_bear_monitor.regime_judge import RegimeJudge
        judge = RegimeJudge()

        bond_df, usdcny_df, div_df = self._make_signal_dfs(
            [1, 0, -1], [-1, 0, 1], [0, 0, 0]
        )
        signals = judge.judge(bond_df, usdcny_df, div_df)
        for s in signals:
            assert s.regime == 'NEUTRAL'

    def test_empty_input(self):
        from data_analyst.bull_bear_monitor.regime_judge import RegimeJudge
        judge = RegimeJudge()

        empty = pd.DataFrame(columns=['cn_10y_signal', 'cn_10y_value', 'cn_10y_ma20', 'cn_10y_trend'])
        empty2 = pd.DataFrame(columns=['usdcny_signal', 'usdcny_value', 'usdcny_ma20', 'usdcny_trend'])
        empty3 = pd.DataFrame(columns=['dividend_signal', 'dividend_relative', 'dividend_rel_ma20', 'dividend_trend'])
        signals = judge.judge(empty, empty2, empty3)
        assert signals == []

    def test_missing_dividend_signal_filled_with_zero(self):
        """When dividend signal has NaN, it should be filled with 0."""
        from data_analyst.bull_bear_monitor.regime_judge import RegimeJudge
        judge = RegimeJudge()

        dates = pd.date_range('2025-06-01', periods=3, freq='B')

        bond_df = pd.DataFrame({
            'cn_10y_value': [2.3] * 3,
            'cn_10y_ma20': [2.4] * 3,
            'cn_10y_trend': ['DOWN'] * 3,
            'cn_10y_signal': [1, 1, 1],
        }, index=dates)

        usdcny_df = pd.DataFrame({
            'usdcny_value': [7.1] * 3,
            'usdcny_ma20': [7.15] * 3,
            'usdcny_trend': ['DOWN'] * 3,
            'usdcny_signal': [1, 1, 1],
        }, index=dates)

        # Only 2 of 3 dates have dividend data
        dividend_df = pd.DataFrame({
            'dividend_relative': [1.5, 1.5],
            'dividend_rel_ma20': [1.55, 1.55],
            'dividend_trend': ['DOWN', 'DOWN'],
            'dividend_signal': [1, -1],
        }, index=dates[:2])

        signals = judge.judge(bond_df, usdcny_df, dividend_df)
        assert len(signals) == 3
        # Third date: dividend_signal filled as 0, so 1+1+0=2 => BULL
        assert signals[2].composite_score == 2
        assert signals[2].dividend_signal == 0


# ---------------------------------------------------------------------------
# Test DDL param count consistency
# ---------------------------------------------------------------------------

class TestStorageParamCount:
    def test_upsert_sql_param_count(self):
        from data_analyst.bull_bear_monitor.storage import UPSERT_SQL
        # Count %s placeholders
        count = UPSERT_SQL.count('%s')
        assert count == 15, f"Expected 15 placeholders, got {count}"

    def test_signal_to_params_count(self):
        from data_analyst.bull_bear_monitor.storage import BullBearStorage
        from data_analyst.bull_bear_monitor.schemas import BullBearSignal
        s = BullBearSignal(calc_date=date(2026, 1, 1), composite_score=0, regime='NEUTRAL')
        params = BullBearStorage._signal_to_params(s)
        assert len(params) == 15, f"Expected 15 params, got {len(params)}"
