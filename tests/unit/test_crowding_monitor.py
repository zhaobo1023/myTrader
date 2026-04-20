# -*- coding: utf-8 -*-
"""
Unit tests for risk_manager/crowding/ module.

Pure-Python tests: no DB, no network.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date


# ---------------------------------------------------------------------------
# Test CrowdingConfig
# ---------------------------------------------------------------------------

class TestCrowdingConfig:
    def test_default_values(self):
        from risk_manager.crowding.config import CrowdingConfig
        cfg = CrowdingConfig()
        assert cfg.hhi_rolling_window == 20
        assert cfg.percentile_lookback == 250
        assert cfg.svd_critical_threshold == 0.50
        assert 'turnover_hhi' in cfg.weights
        assert abs(sum(cfg.weights.values()) - 1.0) < 1e-9

    def test_level_thresholds_order(self):
        from risk_manager.crowding.config import CrowdingConfig
        cfg = CrowdingConfig()
        assert cfg.level_thresholds['LOW'] < cfg.level_thresholds['MEDIUM']
        assert cfg.level_thresholds['MEDIUM'] < cfg.level_thresholds['HIGH']
        assert cfg.level_thresholds['HIGH'] < cfg.level_thresholds['CRITICAL']


# ---------------------------------------------------------------------------
# Test CrowdingScore schema
# ---------------------------------------------------------------------------

class TestCrowdingScore:
    def test_create_score(self):
        from risk_manager.crowding.schemas import CrowdingScore
        s = CrowdingScore(
            calc_date=date(2026, 4, 20),
            crowding_score=55.5,
            crowding_level='HIGH',
        )
        assert s.dimension == 'overall'
        assert s.dimension_id == ''
        assert s.crowding_score == 55.5

    def test_ddl_string(self):
        from risk_manager.crowding.schemas import CROWDING_SCORE_DDL
        assert 'trade_crowding_score' in CROWDING_SCORE_DDL
        assert 'uk_date_dim' in CROWDING_SCORE_DDL


# ---------------------------------------------------------------------------
# Test HHIEngine
# ---------------------------------------------------------------------------

class TestHHIEngine:
    def _make_turnover_df(self, n_days=30, n_industries=5, equal=False):
        """Create mock turnover data."""
        rows = []
        dates = pd.date_range('2025-01-01', periods=n_days, freq='B')
        industries = [f'Industry_{i}' for i in range(n_industries)]

        for d in dates:
            if equal:
                # Equal distribution across industries
                for ind in industries:
                    rows.append({
                        'trade_date': d,
                        'stock_code': f'{ind}_001',
                        'turnover_amount': 1000.0,
                        'sw_level1': ind,
                    })
            else:
                # First industry dominates
                for i, ind in enumerate(industries):
                    amount = 5000.0 if i == 0 else 100.0
                    rows.append({
                        'trade_date': d,
                        'stock_code': f'{ind}_001',
                        'turnover_amount': amount,
                        'sw_level1': ind,
                    })

        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        return df

    def test_hhi_equal_distribution(self):
        """Equal distribution across N industries => HHI = 1/N"""
        from risk_manager.crowding.hhi_engine import HHIEngine
        engine = HHIEngine()

        df = self._make_turnover_df(n_days=5, n_industries=5, equal=True)
        hhi = engine.compute_daily_hhi(df)

        assert not hhi.empty
        # HHI for equal 5-way split: each share = 0.2, HHI = 5 * 0.04 = 0.2
        for val in hhi['hhi']:
            assert abs(val - 0.2) < 0.001

    def test_hhi_concentrated(self):
        """One dominant industry => HHI close to 1"""
        from risk_manager.crowding.hhi_engine import HHIEngine
        engine = HHIEngine()

        df = self._make_turnover_df(n_days=5, n_industries=5, equal=False)
        hhi = engine.compute_daily_hhi(df)

        # First industry: 5000 / (5000 + 4*100) = 5000/5400 ~ 0.926
        # HHI ~ 0.926^2 + 4*(100/5400)^2 ~ 0.857 + 0.001 ~ 0.86
        for val in hhi['hhi']:
            assert val > 0.5  # much higher than equal distribution

    def test_hhi_empty_input(self):
        from risk_manager.crowding.hhi_engine import HHIEngine
        engine = HHIEngine()
        result = engine.compute_daily_hhi(pd.DataFrame())
        assert 'hhi' in result.columns
        assert len(result) == 0

    def test_rolling_hhi(self):
        """Test rolling mean and percentile computation."""
        from risk_manager.crowding.config import CrowdingConfig
        from risk_manager.crowding.hhi_engine import HHIEngine

        cfg = CrowdingConfig(hhi_rolling_window=5, percentile_lookback=10)
        engine = HHIEngine(cfg)

        dates = pd.date_range('2025-01-01', periods=20, freq='B')
        hhi_daily = pd.DataFrame({'hhi': np.linspace(0.05, 0.15, 20)}, index=dates)
        hhi_daily.index.name = 'trade_date'

        result = engine.compute_rolling_hhi(hhi_daily)

        assert 'hhi_rolling' in result.columns
        assert 'hhi_percentile' in result.columns
        # First 4 rows of hhi_rolling should be NaN (window=5)
        assert pd.isna(result['hhi_rolling'].iloc[0])
        # Later values should be valid
        assert not pd.isna(result['hhi_rolling'].iloc[-1])


# ---------------------------------------------------------------------------
# Test CrowdingScorer
# ---------------------------------------------------------------------------

class TestCrowdingScorer:
    def test_score_component_turnover_hhi(self):
        from risk_manager.crowding.crowding_scorer import CrowdingScorer
        scorer = CrowdingScorer()

        assert scorer.score_component(0.0, 'turnover_hhi') == 0.0
        assert scorer.score_component(0.5, 'turnover_hhi') == 50.0
        assert scorer.score_component(1.0, 'turnover_hhi') == 100.0

    def test_score_component_northbound(self):
        from risk_manager.crowding.crowding_scorer import CrowdingScorer
        scorer = CrowdingScorer()

        assert scorer.score_component(0.0, 'northbound_deviation') == 0.0
        assert abs(scorer.score_component(1.5, 'northbound_deviation') - 50.0) < 0.1
        assert scorer.score_component(3.0, 'northbound_deviation') == 100.0
        # Negative deviation also counts (absolute)
        assert abs(scorer.score_component(-1.5, 'northbound_deviation') - 50.0) < 0.1

    def test_score_component_svd(self):
        from risk_manager.crowding.crowding_scorer import CrowdingScorer
        scorer = CrowdingScorer()

        assert scorer.score_component(0.20, 'svd_factor_concentration') == 0.0
        assert abs(scorer.score_component(0.35, 'svd_factor_concentration') - 50.0) < 0.1
        assert scorer.score_component(0.50, 'svd_factor_concentration') == 100.0
        # Below 0.20 => clamped to 0
        assert scorer.score_component(0.10, 'svd_factor_concentration') == 0.0

    def test_level_determination(self):
        """Test that crowding levels are assigned correctly."""
        from risk_manager.crowding.config import CrowdingConfig
        from risk_manager.crowding.crowding_scorer import CrowdingScorer

        cfg = CrowdingConfig()
        scorer = CrowdingScorer(cfg)

        # Build minimal HHI data with known percentiles
        dates = pd.date_range('2025-06-01', periods=5, freq='B')

        # Test with HIGH score (percentile = 0.80 => score = 80)
        hhi_df = pd.DataFrame({
            'hhi': [0.1] * 5,
            'hhi_rolling': [0.1] * 5,
            'hhi_percentile': [0.80] * 5,  # 80th percentile
        }, index=dates)

        north_df = pd.DataFrame(columns=['value'])
        svd_df = pd.DataFrame(columns=['top1_var_ratio'])

        scores = scorer.compute_scores(hhi_df, north_df, svd_df,
                                       start_date='2025-06-01')
        assert len(scores) == 5
        # With only HHI at 80th percentile => score = 80 => HIGH
        for s in scores:
            assert s.crowding_level == 'HIGH'
            assert s.crowding_score == 80.0

    def test_northbound_deviation_computation(self):
        from risk_manager.crowding.config import CrowdingConfig
        from risk_manager.crowding.crowding_scorer import CrowdingScorer

        cfg = CrowdingConfig(north_short_window=3, north_long_window=5)
        scorer = CrowdingScorer(cfg)

        dates = pd.date_range('2025-01-01', periods=10, freq='B')
        north_df = pd.DataFrame({'value': np.linspace(100, 200, 10)}, index=dates)

        result = scorer.compute_northbound_deviation(north_df)
        assert 'deviation' in result.columns
        # First rows: rolling windows not yet full, so std=0 => deviation=0
        assert result['deviation'].iloc[0] == 0.0
        # Last value should be positive (short MA > long MA in rising series)
        last_val = result['deviation'].iloc[-1]
        assert not pd.isna(last_val)
        assert last_val > 0

    def test_empty_hhi_returns_empty(self):
        from risk_manager.crowding.crowding_scorer import CrowdingScorer
        scorer = CrowdingScorer()
        scores = scorer.compute_scores(
            pd.DataFrame(columns=['hhi', 'hhi_rolling', 'hhi_percentile']),
            pd.DataFrame(), pd.DataFrame()
        )
        assert scores == []


# ---------------------------------------------------------------------------
# Test Storage param count
# ---------------------------------------------------------------------------

class TestCrowdingStorageParamCount:
    def test_upsert_sql_param_count(self):
        from risk_manager.crowding.storage import UPSERT_SQL
        count = UPSERT_SQL.count('%s')
        assert count == 10, f"Expected 10 placeholders, got {count}"

    def test_score_to_params_count(self):
        from risk_manager.crowding.storage import CrowdingStorage
        from risk_manager.crowding.schemas import CrowdingScore
        s = CrowdingScore(calc_date=date(2026, 1, 1), crowding_score=50.0, crowding_level='MEDIUM')
        params = CrowdingStorage._score_to_params(s)
        assert len(params) == 10, f"Expected 10 params, got {len(params)}"
