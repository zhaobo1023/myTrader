# -*- coding: utf-8 -*-
"""T5.3 Unit tests for NavCalculator."""

from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from strategist.sim_pool.config import SimPoolConfig
from strategist.sim_pool.nav_calculator import NavCalculator


def _cfg(**kwargs) -> SimPoolConfig:
    defaults = dict(benchmark_code='000300.SH', db_env='local')
    defaults.update(kwargs)
    return SimPoolConfig(**defaults)


def _nav_query_side_effect(initial_cash=1_000_000, shares=1000, price=10.0,
                           entry_cost=10000.0, peak_nav=None,
                           total_buy_cost=100000.0, sell_proceeds=0.0,
                           benchmark_close=1.0, bench_code='000300.SH'):
    """Return a side_effect function for execute_query in NavCalculator."""
    call_count = [0]

    def side_effect(sql, params, **kw):
        call_count[0] += 1
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': initial_cash, 'benchmark_code': bench_code}]
        # SUM queries must be checked before the generic sim_position check
        if 'sim_position' in sql and 'SUM' in sql:
            return [{'total': total_buy_cost}]
        if 'sim_trade_log' in sql and 'SUM' in sql:
            return [{'total': sell_proceeds}]
        if 'sim_position' in sql and 'active' in sql:
            return [{'shares': shares, 'current_price': price, 'entry_cost': entry_cost}]
        if 'sim_daily_nav' in sql and 'MAX(nav)' in sql:
            return [{'peak': peak_nav}] if peak_nav is not None else []
        if 'trade_stock_daily' in sql:
            return [{'close': benchmark_close}]
        return []

    return side_effect


# ---------------------------------------------------------------------------
# T5.3a  nav day1 equals one
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.nav_calculator.execute_update')
@patch('strategist.sim_pool.nav_calculator.execute_query')
def test_nav_day1_equals_one(mock_query, mock_update):
    """Day 1: no prior nav => nav=1.0."""
    # shares=1000, price=10 => portfolio=10000, cash=1000000-100000=900000, total=910000
    # nav = 910000/1000000 = 0.91 ... hmm, not exactly 1.0
    # To get nav=1.0: portfolio_value + cash = initial_cash
    # shares=1000, price=10, entry_cost=10000 => total_buy=10000, cash=990000, total=1000000 => nav=1.0
    mock_query.side_effect = _nav_query_side_effect(
        shares=1000, price=10.0, entry_cost=10000.0,
        peak_nav=None, total_buy_cost=10000.0, sell_proceeds=0.0,
    )
    calc = NavCalculator(config=_cfg())
    result = calc.calculate_daily_nav(pool_id=1, nav_date=date(2026, 4, 15))

    assert result is not None
    assert abs(result['nav'] - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# T5.3b  nav increases with price
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.nav_calculator.execute_update')
@patch('strategist.sim_pool.nav_calculator.execute_query')
def test_nav_increases_with_price(mock_query, mock_update):
    """Stock price +10% => nav > 1.0."""
    # shares=1000, price=11.0 (up 10%), entry_cost=10000
    # portfolio=11000, total_buy=10000, cash=990000, total=1001000, nav=1.001
    mock_query.side_effect = _nav_query_side_effect(
        shares=1000, price=11.0, entry_cost=10000.0,
        peak_nav=None, total_buy_cost=10000.0, sell_proceeds=0.0,
    )
    calc = NavCalculator(config=_cfg())
    result = calc.calculate_daily_nav(pool_id=1, nav_date=date(2026, 4, 15))

    assert result is not None
    assert result['nav'] > 1.0, 'NAV should be above 1.0 when stock price rises'


# ---------------------------------------------------------------------------
# T5.3c  drawdown calculation
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.nav_calculator.execute_update')
@patch('strategist.sim_pool.nav_calculator.execute_query')
def test_drawdown_calculation(mock_query, mock_update):
    """Nav goes 1.0 -> 1.2 -> 1.08. Max was 1.2, so DD = (1.08-1.2)/1.2 = -10%."""
    # To get nav=1.08: portfolio_value + cash = 1080000
    # shares=1000, price=10.8 => portfolio=10800, total_buy=10000
    # cash = 1000000 - 10000 + 0 = 990000
    # total = 10800 + 990000 = 1000800 => nav = 1.0008
    # Better: use larger position
    # shares=100000, price=10.8 => portfolio=1080000, total_buy=1000000
    # cash = 1000000 - 1000000 + 0 = 0
    # total = 1080000, nav = 1.08. Peak = 1.2 => DD = (1.08-1.2)/1.2 = -0.10
    mock_query.side_effect = _nav_query_side_effect(
        shares=100000, price=10.8, entry_cost=1000000.0,
        peak_nav=1.2, total_buy_cost=1000000.0, sell_proceeds=0.0,
    )
    calc = NavCalculator(config=_cfg())
    result = calc.calculate_daily_nav(pool_id=1, nav_date=date(2026, 4, 15))

    assert result is not None
    dd = result.get('drawdown', 0)
    assert abs(dd - (-0.10)) < 0.01, f'Expected DD ~-10%, got {dd}'


# ---------------------------------------------------------------------------
# T5.3d  benchmark_nav fetched from trade_stock_daily
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.nav_calculator.execute_update')
@patch('strategist.sim_pool.nav_calculator.execute_query')
def test_benchmark_nav_fetched(mock_query, mock_update):
    """benchmark_nav should be computed from trade_stock_daily."""
    call_idx = [0]
    bm_close = 4200.5
    bm_first_close = 4000.0  # entry date close
    bm_query_count = [0]

    def side_effect(sql, params, **kw):
        call_idx[0] += 1
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': 1_000_000, 'benchmark_code': '000300.SH'}]
        if 'sim_position' in sql and 'SUM' in sql:
            return [{'total': 10000}]
        if 'sim_trade_log' in sql and 'SUM' in sql:
            return [{'total': 0}]
        if 'sim_position' in sql and 'active' in sql:
            return [{'shares': 1000, 'current_price': 10.0, 'entry_cost': 10000.0}]
        if 'sim_daily_nav' in sql and 'MAX(nav)' in sql:
            return []
        if 'sim_pool' in sql and 'entry_date' in sql:
            return [{'entry_date': '2026-01-01'}]
        if 'trade_stock_daily' in sql:
            bm_query_count[0] += 1
            # First call: today's close; Second call: first close (for bm_nav base)
            if bm_query_count[0] == 1:
                return [{'close': bm_close}]
            else:
                return [{'close': bm_first_close}]
        return []

    mock_query.side_effect = side_effect
    calc = NavCalculator(config=_cfg())
    result = calc.calculate_daily_nav(pool_id=1, nav_date=date(2026, 4, 15))

    assert result is not None
    assert result.get('benchmark_nav') is not None
    expected_bm_nav = bm_close / bm_first_close
    assert abs(result['benchmark_nav'] - expected_bm_nav) < 1e-6
