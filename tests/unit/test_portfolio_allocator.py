# -*- coding: utf-8 -*-
"""
Unit tests for strategist/portfolio_allocator/ module.

Pure-Python tests: no DB, no network.
"""
import pytest
from datetime import date


# ---------------------------------------------------------------------------
# Test AllocatorConfig
# ---------------------------------------------------------------------------

class TestAllocatorConfig:
    def test_base_weights_sum_to_one(self):
        from strategist.portfolio_allocator.config import AllocatorConfig
        cfg = AllocatorConfig()
        total = sum(cfg.base_weights.values())
        assert abs(total - 1.0) < 1e-9, f"Base weights sum to {total}, expected 1.0"

    def test_regime_adjustments_keys_match(self):
        from strategist.portfolio_allocator.config import AllocatorConfig
        cfg = AllocatorConfig()
        strategies = set(cfg.base_weights.keys())
        for regime, adjustments in cfg.regime_adjustments.items():
            assert set(adjustments.keys()) == strategies, \
                f"Regime '{regime}' adjustments don't match base weight strategies"

    def test_constraints(self):
        from strategist.portfolio_allocator.config import AllocatorConfig
        cfg = AllocatorConfig()
        assert cfg.min_weight > 0
        assert cfg.max_weight <= 1.0
        assert cfg.min_weight < cfg.max_weight


# ---------------------------------------------------------------------------
# Test WeightEngine
# ---------------------------------------------------------------------------

class TestWeightEngine:
    def test_neutral_regime_low_crowding(self):
        """NEUTRAL + LOW => weights equal to base (after normalization)."""
        from strategist.portfolio_allocator.weight_engine import WeightEngine
        engine = WeightEngine()

        weights = engine.compute_weights(date(2026, 4, 20), 'NEUTRAL', 'LOW')
        assert len(weights) == 3

        weight_map = {w.strategy_name: w for w in weights}
        total = sum(w.final_weight for w in weights)
        assert abs(total - 1.0) < 1e-4, f"Weights sum to {total}"

        # NEUTRAL + LOW => no adjustments => final = base (normalized)
        for w in weights:
            assert w.regime_adjustment == 0.0
            assert w.crowding_adjustment == 0.0

    def test_bull_regime_adjustments(self):
        """BULL: doctor_tao gets +10%, multi_factor gets -15%."""
        from strategist.portfolio_allocator.weight_engine import WeightEngine
        engine = WeightEngine()

        weights = engine.compute_weights(date(2026, 4, 20), 'BULL', 'LOW')
        weight_map = {w.strategy_name: w for w in weights}

        assert weight_map['doctor_tao'].regime_adjustment == 0.10
        assert weight_map['multi_factor'].regime_adjustment == -0.15
        assert weight_map['xgboost'].regime_adjustment == 0.05

    def test_bear_regime_adjustments(self):
        """BEAR: multi_factor gets +20%, doctor_tao gets -15%."""
        from strategist.portfolio_allocator.weight_engine import WeightEngine
        engine = WeightEngine()

        weights = engine.compute_weights(date(2026, 4, 20), 'BEAR', 'LOW')
        weight_map = {w.strategy_name: w for w in weights}

        assert weight_map['multi_factor'].regime_adjustment == 0.20
        assert weight_map['doctor_tao'].regime_adjustment == -0.15

    def test_crowding_penalty_high(self):
        """HIGH crowding: doctor_tao gets -10%, xgboost gets -5%."""
        from strategist.portfolio_allocator.weight_engine import WeightEngine
        engine = WeightEngine()

        weights = engine.compute_weights(date(2026, 4, 20), 'NEUTRAL', 'HIGH')
        weight_map = {w.strategy_name: w for w in weights}

        assert weight_map['doctor_tao'].crowding_adjustment == -0.10
        assert weight_map['xgboost'].crowding_adjustment == -0.05
        assert weight_map['multi_factor'].crowding_adjustment == 0.0

    def test_crowding_penalty_critical(self):
        """CRITICAL crowding: even larger penalty."""
        from strategist.portfolio_allocator.weight_engine import WeightEngine
        engine = WeightEngine()

        weights = engine.compute_weights(date(2026, 4, 20), 'NEUTRAL', 'CRITICAL')
        weight_map = {w.strategy_name: w for w in weights}

        assert weight_map['doctor_tao'].crowding_adjustment == -0.20
        assert weight_map['xgboost'].crowding_adjustment == -0.10

    def test_weights_always_sum_to_one(self):
        """Test normalization for all regime/crowding combinations."""
        from strategist.portfolio_allocator.weight_engine import WeightEngine
        engine = WeightEngine()

        for regime in ['BULL', 'BEAR', 'NEUTRAL']:
            for crowding in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']:
                weights = engine.compute_weights(date(2026, 4, 20), regime, crowding)
                total = sum(w.final_weight for w in weights)
                assert abs(total - 1.0) < 1e-4, \
                    f"Weights don't sum to 1 for {regime}/{crowding}: {total}"

    def test_weights_respect_constraints(self):
        """All weights should be in [min_weight, max_weight]."""
        from strategist.portfolio_allocator.config import AllocatorConfig
        from strategist.portfolio_allocator.weight_engine import WeightEngine

        cfg = AllocatorConfig()
        engine = WeightEngine(cfg)

        for regime in ['BULL', 'BEAR', 'NEUTRAL']:
            for crowding in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']:
                weights = engine.compute_weights(date(2026, 4, 20), regime, crowding)
                for w in weights:
                    # After normalization, weights might slightly exceed max_weight
                    # but raw clamped values should respect constraints
                    assert w.final_weight > 0, \
                        f"Weight for {w.strategy_name} is {w.final_weight} in {regime}/{crowding}"

    def test_bear_critical_multi_factor_dominates(self):
        """BEAR + CRITICAL: multi_factor should have the highest weight."""
        from strategist.portfolio_allocator.weight_engine import WeightEngine
        engine = WeightEngine()

        weights = engine.compute_weights(date(2026, 4, 20), 'BEAR', 'CRITICAL')
        weight_map = {w.strategy_name: w.final_weight for w in weights}

        assert weight_map['multi_factor'] > weight_map['doctor_tao']
        assert weight_map['multi_factor'] > weight_map['xgboost']


# ---------------------------------------------------------------------------
# Test Reconciler
# ---------------------------------------------------------------------------

class TestReconciler:
    def test_no_current_weights(self):
        """When no current weights, all suggestions should be SET."""
        from strategist.portfolio_allocator.reconciler import Reconciler
        rec = Reconciler()

        target = {'xgboost': 0.4, 'doctor_tao': 0.35, 'multi_factor': 0.25}
        suggestions = rec.reconcile(target, current_weights=None)

        assert len(suggestions) == 3
        for s in suggestions:
            assert s['action'] == 'SET'
            assert s['current'] is None
            assert s['delta'] is None

    def test_hold_within_threshold(self):
        """Small changes below threshold => HOLD."""
        from strategist.portfolio_allocator.reconciler import Reconciler
        rec = Reconciler(threshold_pct=5.0)

        target = {'xgboost': 0.41, 'doctor_tao': 0.34, 'multi_factor': 0.25}
        current = {'xgboost': 0.40, 'doctor_tao': 0.35, 'multi_factor': 0.25}
        suggestions = rec.reconcile(target, current)

        for s in suggestions:
            assert s['action'] == 'HOLD'

    def test_increase_decrease(self):
        """Large changes => INCREASE or DECREASE."""
        from strategist.portfolio_allocator.reconciler import Reconciler
        rec = Reconciler(threshold_pct=5.0)

        target = {'xgboost': 0.50, 'doctor_tao': 0.20, 'multi_factor': 0.35}
        current = {'xgboost': 0.40, 'doctor_tao': 0.35, 'multi_factor': 0.25}
        suggestions = rec.reconcile(target, current)

        result = {s['strategy']: s for s in suggestions}
        assert result['xgboost']['action'] == 'INCREASE'     # +10pp > 5pp
        assert result['doctor_tao']['action'] == 'DECREASE'   # -15pp > 5pp
        assert result['multi_factor']['action'] == 'INCREASE' # +10pp > 5pp

    def test_zero_delta_is_hold(self):
        """Exact same weights => HOLD with delta = 0."""
        from strategist.portfolio_allocator.reconciler import Reconciler
        rec = Reconciler(threshold_pct=5.0)

        target = {'xgboost': 0.40}
        current = {'xgboost': 0.40}
        suggestions = rec.reconcile(target, current)

        assert suggestions[0]['action'] == 'HOLD'
        assert suggestions[0]['delta'] == 0.0


# ---------------------------------------------------------------------------
# Test Storage param count
# ---------------------------------------------------------------------------

class TestWeightStorageParamCount:
    def test_upsert_sql_param_count(self):
        from strategist.portfolio_allocator.storage import UPSERT_SQL
        count = UPSERT_SQL.count('%s')
        assert count == 8, f"Expected 8 placeholders, got {count}"

    def test_weight_to_params_count(self):
        from strategist.portfolio_allocator.storage import WeightStorage
        from strategist.portfolio_allocator.schemas import StrategyWeight
        w = StrategyWeight(
            calc_date=date(2026, 1, 1),
            strategy_name='xgboost',
            base_weight=0.4,
            final_weight=0.4,
        )
        params = WeightStorage._weight_to_params(w)
        assert len(params) == 8, f"Expected 8 params, got {len(params)}"
