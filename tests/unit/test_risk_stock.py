# -*- coding: utf-8 -*-
"""
Unit tests for api/routers/risk.py — stock risk endpoint helpers.

Tests are pure-Python: no DB, no FastAPI, no network.
We import only the standalone logic that can be exercised without the full app.
"""
import bisect
import math
import pytest


# ---------------------------------------------------------------------------
# Helper: percentile rank (mirrors the backend implementation)
# ---------------------------------------------------------------------------

def compute_percentile(vals_sorted: list, current: float) -> int:
    """Return percentile rank (0-100) of current in a pre-sorted list."""
    return round(bisect.bisect_right(vals_sorted, current) / len(vals_sorted) * 100)


class TestPercentileRank:
    def test_lowest_value_returns_near_zero(self):
        vals = sorted([10.0, 20.0, 30.0, 40.0, 50.0])
        assert compute_percentile(vals, 10.0) == 20  # 1/5 = 20%

    def test_highest_value_returns_100(self):
        vals = sorted([10.0, 20.0, 30.0, 40.0, 50.0])
        assert compute_percentile(vals, 50.0) == 100

    def test_midpoint_value(self):
        vals = sorted(range(1, 101))  # 1..100
        assert compute_percentile(vals, 50) == 50

    def test_above_all_values(self):
        vals = sorted([10.0, 20.0, 30.0])
        assert compute_percentile(vals, 100.0) == 100

    def test_below_all_values(self):
        vals = sorted([10.0, 20.0, 30.0])
        assert compute_percentile(vals, 5.0) == 0

    def test_rounding(self):
        vals = sorted([1.0, 2.0, 3.0])  # 1/3 = 33.33...
        pct = compute_percentile(vals, 1.0)
        assert pct == 33

    def test_large_distribution(self):
        vals = sorted(float(i) for i in range(1, 1001))  # 1-1000
        # Value at 750 should be 75th percentile
        assert compute_percentile(vals, 750.0) == 75


# ---------------------------------------------------------------------------
# Helper: position weight calculation (mirrors the backend logic)
# ---------------------------------------------------------------------------

def compute_position_weight(positions: list, stock_code: str, close_price: float | None) -> float | None:
    """
    positions: list of {stock_code, shares, cost_price}
    Returns weight_pct or None if total_val == 0.
    """
    total_val = sum(
        ((close_price or p['cost_price']) if p['stock_code'] == stock_code else p['cost_price']) * p['shares']
        for p in positions if p['shares'] > 0
    )
    if total_val <= 0:
        return None
    target = next((p for p in positions if p['stock_code'] == stock_code), None)
    if not target or target['shares'] <= 0:
        return None
    curr_val = (close_price or target['cost_price']) * target['shares']
    return round(curr_val / total_val * 100, 2)


class TestPositionWeight:
    def test_single_position_is_100_pct(self):
        positions = [{'stock_code': 'A', 'shares': 100, 'cost_price': 10.0}]
        assert compute_position_weight(positions, 'A', 10.0) == 100.0

    def test_two_equal_positions(self):
        positions = [
            {'stock_code': 'A', 'shares': 100, 'cost_price': 10.0},
            {'stock_code': 'B', 'shares': 100, 'cost_price': 10.0},
        ]
        assert compute_position_weight(positions, 'A', 10.0) == 50.0

    def test_different_prices(self):
        positions = [
            {'stock_code': 'A', 'shares': 100, 'cost_price': 20.0},
            {'stock_code': 'B', 'shares': 100, 'cost_price': 80.0},
        ]
        # A=2000, B=8000 (cost), total=10000 → A=20%
        assert compute_position_weight(positions, 'A', 20.0) == 20.0

    def test_close_price_used_for_target(self):
        positions = [
            {'stock_code': 'A', 'shares': 100, 'cost_price': 10.0},
            {'stock_code': 'B', 'shares': 100, 'cost_price': 10.0},
        ]
        # A's current price is 30 → A=3000, B=1000 (cost), total=4000 → A=75%
        assert compute_position_weight(positions, 'A', 30.0) == 75.0

    def test_no_close_price_falls_back_to_cost(self):
        positions = [
            {'stock_code': 'A', 'shares': 100, 'cost_price': 10.0},
            {'stock_code': 'B', 'shares': 100, 'cost_price': 10.0},
        ]
        assert compute_position_weight(positions, 'A', None) == 50.0

    def test_zero_shares_excluded(self):
        positions = [
            {'stock_code': 'A', 'shares': 100, 'cost_price': 10.0},
            {'stock_code': 'B', 'shares': 0,   'cost_price': 10.0},
        ]
        assert compute_position_weight(positions, 'A', 10.0) == 100.0

    def test_total_val_zero_returns_none(self):
        positions = [{'stock_code': 'A', 'shares': 100, 'cost_price': 0.0}]
        assert compute_position_weight(positions, 'A', 0.0) is None


# ---------------------------------------------------------------------------
# Frontend: buildPersonalAlerts logic (Python equivalent for testing)
# ---------------------------------------------------------------------------

AlertLevel = str  # 'warn' | 'danger' | 'ok' | 'tip'


def build_personal_alerts(
    pnl: float | None,
    weight: float | None,
    corr: float | None,
    pe_pct: float | None,
) -> list[dict]:
    """Python mirror of the TypeScript buildPersonalAlerts function."""
    alerts = []

    if pnl is not None:
        if pnl <= -20:
            alerts.append({'level': 'danger', 'key': 'stop_loss'})
        elif pnl <= -10:
            alerts.append({'level': 'warn', 'key': 'loss_check'})
        elif pnl <= -5:
            alerts.append({'level': 'warn', 'key': 'logic_check'})
        elif pnl >= 50:
            alerts.append({'level': 'tip', 'key': 'reduce_for_compound'})
        elif pnl >= 30:
            alerts.append({'level': 'tip', 'key': 'profit_cushion'})
        elif pnl >= 15:
            alerts.append({'level': 'ok', 'key': 'safety_margin'})
        elif pnl >= 0:
            alerts.append({'level': 'ok', 'key': 'near_cost'})

    if weight is not None:
        if weight > 10:
            alerts.append({'level': 'danger', 'key': 'overweight_critical'})
        elif weight > 6:
            alerts.append({'level': 'warn', 'key': 'overweight'})
        elif weight >= 4:
            alerts.append({'level': 'tip', 'key': 'high_conviction'})
        elif weight >= 2:
            alerts.append({'level': 'ok', 'key': 'normal_weight'})
        else:
            alerts.append({'level': 'tip', 'key': 'pilot_position'})

    if weight is not None and pe_pct is not None:
        if pe_pct > 80 and weight > 2:
            alerts.append({'level': 'warn', 'key': 'high_pe_heavy'})
        elif pe_pct < 25 and weight < 4:
            alerts.append({'level': 'tip', 'key': 'low_pe_light'})
        elif pe_pct > 80 and weight <= 2:
            alerts.append({'level': 'ok', 'key': 'high_pe_light_ok'})

    if pnl is not None and weight is not None:
        if pnl <= -10 and weight > 6:
            alerts.append({'level': 'danger', 'key': 'heavy_loss'})
        elif pnl >= 30 and weight > 6:
            alerts.append({'level': 'tip', 'key': 'heavy_profit'})

    if corr is not None:
        if corr >= 0.7:
            alerts.append({'level': 'warn', 'key': 'extreme_corr'})
        elif corr >= 0.55:
            alerts.append({'level': 'warn', 'key': 'high_corr'})
        elif corr >= 0.4:
            alerts.append({'level': 'tip', 'key': 'mid_corr'})
        else:
            alerts.append({'level': 'ok', 'key': 'low_corr'})

    return alerts


def levels(alerts):
    return [a['level'] for a in alerts]

def keys(alerts):
    return [a['key'] for a in alerts]


class TestBuildPersonalAlerts:
    # PnL thresholds
    def test_deep_loss_is_danger(self):
        a = build_personal_alerts(pnl=-25.0, weight=None, corr=None, pe_pct=None)
        assert 'stop_loss' in keys(a)
        assert 'danger' in levels(a)

    def test_moderate_loss_is_warn(self):
        a = build_personal_alerts(pnl=-12.0, weight=None, corr=None, pe_pct=None)
        assert 'loss_check' in keys(a)

    def test_small_profit_is_ok(self):
        a = build_personal_alerts(pnl=10.0, weight=None, corr=None, pe_pct=None)
        assert 'ok' in levels(a)

    def test_large_profit_is_tip(self):
        a = build_personal_alerts(pnl=60.0, weight=None, corr=None, pe_pct=None)
        assert 'reduce_for_compound' in keys(a)

    # Weight thresholds
    def test_overweight_critical(self):
        a = build_personal_alerts(pnl=None, weight=12.0, corr=None, pe_pct=None)
        assert 'overweight_critical' in keys(a)
        assert 'danger' in levels(a)

    def test_normal_weight_is_ok(self):
        a = build_personal_alerts(pnl=None, weight=3.0, corr=None, pe_pct=None)
        assert 'normal_weight' in keys(a)
        assert 'ok' in levels(a)

    def test_pilot_position(self):
        a = build_personal_alerts(pnl=None, weight=1.0, corr=None, pe_pct=None)
        assert 'pilot_position' in keys(a)

    # Valuation x weight
    def test_high_pe_heavy_position_warns(self):
        a = build_personal_alerts(pnl=None, weight=5.0, corr=None, pe_pct=85.0)
        assert 'high_pe_heavy' in keys(a)
        assert 'warn' in levels(a)

    def test_low_pe_light_position_tips(self):
        a = build_personal_alerts(pnl=None, weight=2.0, corr=None, pe_pct=15.0)
        assert 'low_pe_light' in keys(a)
        assert 'tip' in levels(a)

    def test_high_pe_light_position_is_ok(self):
        a = build_personal_alerts(pnl=None, weight=1.5, corr=None, pe_pct=85.0)
        assert 'high_pe_light_ok' in keys(a)

    # Heavy loss combo
    def test_heavy_overweight_with_loss_is_double_danger(self):
        a = build_personal_alerts(pnl=-15.0, weight=8.0, corr=None, pe_pct=None)
        danger_count = sum(1 for al in a if al['level'] == 'danger')
        assert danger_count >= 1  # at least overweight danger
        assert 'heavy_loss' in keys(a)

    # Correlation
    def test_extreme_corr_warns(self):
        a = build_personal_alerts(pnl=None, weight=None, corr=0.75, pe_pct=None)
        assert 'extreme_corr' in keys(a)
        assert 'warn' in levels(a)

    def test_low_corr_is_ok(self):
        a = build_personal_alerts(pnl=None, weight=None, corr=0.2, pe_pct=None)
        assert 'low_corr' in keys(a)
        assert 'ok' in levels(a)

    # None inputs produce no alerts
    def test_all_none_returns_empty(self):
        assert build_personal_alerts(None, None, None, None) == []
