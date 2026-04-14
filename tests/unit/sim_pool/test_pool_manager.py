# -*- coding: utf-8 -*-
"""T5.1 Unit tests for PoolManager."""

from unittest.mock import patch, MagicMock, call
import pandas as pd
import pytest

from strategist.sim_pool.config import SimPoolConfig
from strategist.sim_pool.pool_manager import PoolManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_signals(n: int) -> pd.DataFrame:
    return pd.DataFrame({
        'stock_code': [f'00000{i}' for i in range(n)],
        'stock_name': [f'Stock{i}' for i in range(n)],
    })


def _default_config(**kwargs) -> SimPoolConfig:
    defaults = dict(
        max_positions=10,
        initial_cash=1_000_000,
        benchmark_code='000300.SH',
        db_env='local',
    )
    defaults.update(kwargs)
    return SimPoolConfig(**defaults)


# ---------------------------------------------------------------------------
# T5.1a  create_pool writes DB
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.pool_manager.execute_query')
@patch('strategist.sim_pool.pool_manager.execute_update')
def test_create_pool_writes_db(mock_update, mock_query):
    """create_pool calls execute_update for sim_pool + N positions."""
    mock_query.return_value = [{'id': 42}]

    mgr = PoolManager(config=_default_config())
    signals = _make_signals(3)

    pool_id = mgr.create_pool(
        strategy_id=1,
        strategy_type='momentum',
        name='test_pool',
        signal_date=__import__('datetime').date(2026, 4, 14),
        signals_df=signals,
    )

    assert pool_id == 42
    # execute_update called: 1 for sim_pool + 3 for positions
    assert mock_update.call_count == 4


# ---------------------------------------------------------------------------
# T5.1b  equal weight
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.pool_manager.execute_query')
@patch('strategist.sim_pool.pool_manager.execute_update')
def test_create_pool_equal_weight(mock_update, mock_query):
    """5 stocks => each weight=0.2 (1/5)."""
    mock_query.return_value = [{'id': 1}]
    mgr = PoolManager(config=_default_config())
    signals = _make_signals(5)
    mgr.create_pool(1, 'momentum', 'test', __import__('datetime').date(2026, 4, 14), signals)

    # Collect all position INSERT calls (after the first sim_pool INSERT)
    position_calls = mock_update.call_args_list[1:]
    for c in position_calls:
        args = c[0][1]   # positional tuple passed to execute_update
        weight = args[3]
        assert abs(weight - 0.2) < 1e-6, f'Expected weight 0.2, got {weight}'


# ---------------------------------------------------------------------------
# T5.1c  max_positions cap
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.pool_manager.execute_query')
@patch('strategist.sim_pool.pool_manager.execute_update')
def test_create_pool_max_positions(mock_update, mock_query):
    """15 signals + max_positions=10 => only 10 positions created."""
    mock_query.return_value = [{'id': 1}]
    cfg = _default_config(max_positions=10)
    mgr = PoolManager(config=cfg)
    signals = _make_signals(15)
    mgr.create_pool(1, 'momentum', 'test', __import__('datetime').date(2026, 4, 14), signals)

    # 1 sim_pool + 10 positions
    assert mock_update.call_count == 11


# ---------------------------------------------------------------------------
# T5.1d  list_pools filter by status
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.pool_manager.execute_query')
def test_list_pools_filter_by_status(mock_query):
    """list_pools(status='active') passes correct WHERE clause."""
    mock_query.return_value = [{'id': 1, 'status': 'active', 'params': None}]
    mgr = PoolManager(config=_default_config())
    result = mgr.list_pools(status='active')

    assert len(result) == 1
    sql_call = mock_query.call_args[0][0]
    assert 'status' in sql_call
    params = mock_query.call_args[0][1]
    assert 'active' in params


# ---------------------------------------------------------------------------
# T5.1e  close_pool sets status
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.pool_manager.execute_update')
def test_close_pool_sets_status(mock_update):
    """close_pool fires 2 UPDATE statements: positions and pool."""
    mgr = PoolManager(config=_default_config())
    mgr.close_pool(pool_id=7, reason='manual')

    assert mock_update.call_count == 2
    # First call updates positions
    first_sql = mock_update.call_args_list[0][0][0]
    assert 'sim_position' in first_sql
    # Second call updates pool
    second_sql = mock_update.call_args_list[1][0][0]
    assert 'sim_pool' in second_sql and 'closed' in second_sql
