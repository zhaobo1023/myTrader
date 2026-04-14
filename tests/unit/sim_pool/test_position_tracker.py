# -*- coding: utf-8 -*-
"""T5.2 Unit tests for PositionTracker."""

import math
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from strategist.sim_pool.config import SimPoolConfig
from strategist.sim_pool.position_tracker import PositionTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**kwargs) -> SimPoolConfig:
    defaults = dict(
        commission=0.0003, slippage=0.001, stamp_tax=0.001,
        stop_loss=-0.10, take_profit=0.20, max_hold_days=60,
        max_suspended_days=5, db_env='local',
    )
    defaults.update(kwargs)
    return SimPoolConfig(**defaults)


def _make_pool_row(params_dict=None):
    import json
    cfg = _cfg()
    return [{'initial_cash': 1_000_000, 'params': json.dumps(cfg.to_dict()),
             'entry_date': '2026-01-01'}]


def _make_position(entry_cost=10000.0, current_price=10.0, shares=1000,
                   suspended_days=0, entry_date='2026-01-01', pos_id=1,
                   entry_price=10.0):
    return {
        'id': pos_id, 'stock_code': '000001', 'shares': shares,
        'entry_cost': entry_cost, 'current_price': current_price,
        'entry_price': entry_price, 'entry_date': entry_date,
        'suspended_days': suspended_days,
    }


# ---------------------------------------------------------------------------
# T5.2a  fill_entry_prices calculates cost correctly
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_fill_entry_prices_calculates_cost(mock_query, mock_update):
    """Buy price = close*(1+slippage), shares multiple of 100, commission deducted."""
    close = 10.0
    weight = 0.2
    initial_cash = 1_000_000

    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            import json
            return [{'initial_cash': initial_cash, 'params': json.dumps(_cfg().to_dict())}]
        if 'sim_position' in sql and 'pending' in sql:
            return [{'id': 1, 'stock_code': '000001', 'weight': weight}]
        if 'trade_stock_daily' in sql:
            return [{'stock_code': '000001', 'close': close}]
        return []

    mock_query.side_effect = side_effect

    tracker = PositionTracker(config=_cfg())
    filled = tracker.fill_entry_prices(pool_id=1, entry_date=date(2026, 4, 15))

    assert filled == 1

    # Verify shares are multiple of 100
    pos_update_call = mock_update.call_args_list[0]
    shares_arg = pos_update_call[0][1][2]   # shares is 3rd param in UPDATE sim_position
    assert shares_arg % 100 == 0
    assert shares_arg > 0

    # Expected: cash_alloc=200000, buy_price=10.01, raw=19980, floor to 100=19900
    buy_price = close * (1 + 0.001)
    expected_shares = math.floor((initial_cash * weight / buy_price) / 100) * 100
    assert shares_arg == expected_shares


# ---------------------------------------------------------------------------
# T5.2b  stop_loss triggers exit
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_check_exits_stop_loss(mock_query, mock_update):
    """current_return = -11% => exit_reason='stop_loss'."""
    import json
    cfg = _cfg(stop_loss=-0.10)

    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': 1e6, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': '2026-01-01'}]
        if 'sim_position' in sql and 'active' in sql:
            # entry_cost=10000, current_price=8.9 => return = -11%
            return [_make_position(entry_cost=10000, current_price=8.9,
                                   shares=1000, entry_date='2026-03-01')]
        return []

    mock_query.side_effect = side_effect

    tracker = PositionTracker(config=cfg)
    exited = tracker.check_exits(pool_id=1, price_date=date(2026, 4, 14))

    assert 1 in exited
    # Check UPDATE sim_position was called with stop_loss
    update_sql_calls = [c[0][0] for c in mock_update.call_args_list]
    assert any('stop_loss' in str(c[0][1]) for c in mock_update.call_args_list
               if 'sim_position' in c[0][0])


# ---------------------------------------------------------------------------
# T5.2c  take_profit triggers exit
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_check_exits_take_profit(mock_query, mock_update):
    """current_return = +22% => exit_reason='take_profit'."""
    import json
    cfg = _cfg(take_profit=0.20)

    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': 1e6, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': '2026-01-01'}]
        if 'sim_position' in sql and 'active' in sql:
            return [_make_position(entry_cost=10000, current_price=12.2,
                                   shares=1000, entry_date='2026-03-01')]
        return []

    mock_query.side_effect = side_effect
    tracker = PositionTracker(config=cfg)
    exited = tracker.check_exits(pool_id=1, price_date=date(2026, 4, 14))

    assert 1 in exited
    update_calls_params = [c[0][1] for c in mock_update.call_args_list if 'sim_position' in c[0][0]]
    assert any('take_profit' in str(p) for p in update_calls_params)


# ---------------------------------------------------------------------------
# T5.2d  max_hold triggers exit
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_check_exits_max_hold(mock_query, mock_update):
    """hold_days=61 (> max_hold_days=60) => exit_reason='max_hold'."""
    import json
    cfg = _cfg(max_hold_days=60, stop_loss=-0.10, take_profit=0.20)

    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': 1e6, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': '2026-01-01'}]
        if 'sim_position' in sql and 'active' in sql:
            # return=0% (no profit/loss), but held 61 days
            return [_make_position(entry_cost=10000, current_price=10.0,
                                   shares=1000, entry_date='2026-02-12')]
        return []

    mock_query.side_effect = side_effect
    tracker = PositionTracker(config=cfg)
    # check_date is 61 days after 2026-02-12 = 2026-04-14
    exited = tracker.check_exits(pool_id=1, price_date=date(2026, 4, 14))

    assert 1 in exited
    update_calls_params = [c[0][1] for c in mock_update.call_args_list if 'sim_position' in c[0][0]]
    assert any('max_hold' in str(p) for p in update_calls_params)


# ---------------------------------------------------------------------------
# T5.2e  no exit triggers
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_check_exits_no_trigger(mock_query, mock_update):
    """return=-5%, hold=30 days => no exit."""
    import json
    cfg = _cfg(stop_loss=-0.10, take_profit=0.20, max_hold_days=60)

    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': 1e6, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': '2026-01-01'}]
        if 'sim_position' in sql and 'active' in sql:
            return [_make_position(entry_cost=10000, current_price=9.5,
                                   shares=1000, entry_date='2026-03-15')]
        return []

    mock_query.side_effect = side_effect
    tracker = PositionTracker(config=cfg)
    exited = tracker.check_exits(pool_id=1, price_date=date(2026, 4, 14))

    assert exited == []
    assert mock_update.call_count == 0


# ---------------------------------------------------------------------------
# T5.2f  sell cost includes stamp tax
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_sell_cost_includes_stamp_tax(mock_query, mock_update):
    """Sell side: stamp_tax deducted, net_return < gross_return."""
    import json
    cfg = _cfg(take_profit=0.10, commission=0.0003, stamp_tax=0.001, slippage=0.001)

    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': 1e6, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': '2026-01-01'}]
        if 'sim_position' in sql and 'active' in sql:
            # gross return ~+11% (entry_cost=10000, current_price=11.1*1000=11100)
            return [_make_position(entry_cost=10000, current_price=11.1,
                                   shares=1000, entry_date='2026-03-01')]
        return []

    mock_query.side_effect = side_effect
    tracker = PositionTracker(config=cfg)
    tracker.check_exits(pool_id=1, price_date=date(2026, 4, 14))

    pos_update_params = [c[0][1] for c in mock_update.call_args_list if 'sim_position' in c[0][0]]
    assert len(pos_update_params) == 1
    gross_return = pos_update_params[0][3]
    net_return = pos_update_params[0][4]
    assert net_return < gross_return, 'net_return should be less than gross_return after costs'


# ---------------------------------------------------------------------------
# T5.2g  suspended stock force exit
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_suspended_stock_force_exit(mock_query, mock_update):
    """Suspended >= max_suspended_days => handle_suspended force-exits."""
    import json
    cfg = _cfg(max_suspended_days=5)

    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'params' in sql:
            return [{'params': json.dumps(cfg.to_dict())}]
        if 'suspended_days' in sql and 'active' in sql:
            return [_make_position(entry_cost=10000, current_price=10.0,
                                   shares=1000, suspended_days=6)]
        return []

    mock_query.side_effect = side_effect
    tracker = PositionTracker(config=cfg)
    exited = tracker.handle_suspended(pool_id=1, price_date=date(2026, 4, 14))

    assert 1 in exited
    pos_calls = [c for c in mock_update.call_args_list if 'sim_position' in c[0][0]]
    assert len(pos_calls) >= 1
    # exit_reason='strategy' is hardcoded in the SQL, not a parameter
    assert 'strategy' in pos_calls[0][0][0]
