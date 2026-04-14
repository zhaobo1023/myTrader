# -*- coding: utf-8 -*-
"""T5.6 Integration test: full SimPool lifecycle.

These tests verify the complete flow from pool creation through final report.
They use mocked DB calls to simulate database interactions without requiring
a real database connection.
"""

import json
import math
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, call, ANY

import pandas as pd
import pytest

from strategist.sim_pool.config import SimPoolConfig
from strategist.sim_pool.pool_manager import PoolManager
from strategist.sim_pool.position_tracker import PositionTracker
from strategist.sim_pool.nav_calculator import NavCalculator
from strategist.sim_pool.report_generator import ReportGenerator
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATE_0 = date(2026, 1, 5)   # Monday - signal_date
DATE_1 = date(2026, 1, 6)   # T+1 - fill entry
DATE_2 = date(2026, 1, 7)
DATE_3 = date(2026, 1, 8)
DATE_4 = date(2026, 1, 9)

POOL_ID = 1
INITIAL_CASH = 1_000_000
N_STOCKS = 5
SHARES_PER_STOCK = 1000
ENTRY_PRICE = 10.0  # per share
ENTRY_COST = SHARES_PER_STOCK * ENTRY_PRICE * (1 + 0.0003) + SHARES_PER_STOCK * ENTRY_PRICE * 0.001  # approx

CFG = SimPoolConfig(
    commission=0.0003, slippage=0.001, stamp_tax=0.001,
    stop_loss=-0.10, take_profit=0.20, max_hold_days=60,
    db_env='local',
)
CFG_JSON = json.dumps(CFG.to_dict())


def _signals_df() -> pd.DataFrame:
    return pd.DataFrame({
        'stock_code': [f'60000{i}' for i in range(N_STOCKS)],
        'stock_name': [f'Stock{i}' for i in range(N_STOCKS)],
    })


def _active_positions(prices: dict = None) -> list:
    """Return N active positions with given prices (stock_code -> price)."""
    prices = prices or {f'60000{i}': ENTRY_PRICE for i in range(N_STOCKS)}
    result = []
    for i in range(N_STOCKS):
        code = f'60000{i}'
        price = prices.get(code, ENTRY_PRICE)
        result.append({
            'id': i + 1, 'stock_code': code, 'stock_name': f'Stock{i}',
            'shares': SHARES_PER_STOCK,
            'entry_cost': SHARES_PER_STOCK * ENTRY_PRICE * (1 + 0.001),
            'current_price': price,
            'entry_price': ENTRY_PRICE,
            'entry_date': DATE_1.isoformat(),
            'suspended_days': 0,
            'weight': 0.2,
            'status': 'active',
            'signal_meta': None,
        })
    return result


def _exited_position(pos_id: int, code: str, name: str,
                     exit_reason: str, net_return: float) -> dict:
    return {
        'id': pos_id, 'stock_code': code, 'stock_name': name,
        'shares': SHARES_PER_STOCK, 'entry_cost': ENTRY_COST,
        'exit_price': ENTRY_PRICE * (1 + net_return * 0.9),
        'current_price': ENTRY_PRICE * (1 + net_return),
        'entry_date': DATE_1.isoformat(),
        'exit_date': DATE_4.isoformat(),
        'suspended_days': 0, 'weight': 0.2,
        'status': 'exited', 'exit_reason': exit_reason,
        'net_return': net_return, 'gross_return': net_return * 1.01,
        'signal_meta': None,
    }


_FAKE_METRICS = SimpleNamespace(
    start_date='2026-01-05', end_date='2026-01-09',
    trading_days=4, initial_cash=float(INITIAL_CASH),
    final_value=float(INITIAL_CASH) * 1.02,
    total_return=0.02, annual_return=2.0,
    benchmark_return=0.01, excess_return=0.01,
    max_drawdown=0.03, volatility=0.12,
    sharpe_ratio=1.2, sortino_ratio=1.5, calmar_ratio=2.0,
    total_trades=N_STOCKS, win_trades=3, lose_trades=2,
    win_rate=0.6, avg_return_per_trade=0.004,
    avg_win=0.05, avg_loss=0.03, profit_loss_ratio=1.67,
    avg_hold_days=4,
)


# ---------------------------------------------------------------------------
# T5.6a  Full lifecycle
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.report_generator.execute_update')
@patch('strategist.sim_pool.report_generator.execute_query')
@patch('strategist.sim_pool.nav_calculator.execute_update')
@patch('strategist.sim_pool.nav_calculator.execute_query')
@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
@patch('strategist.sim_pool.pool_manager.execute_update')
@patch('strategist.sim_pool.pool_manager.execute_query')
@patch('strategist.backtest.metrics.MetricsCalculator')
def test_full_lifecycle(mock_calc_cls,
                       mock_pm_query, mock_pm_update,
                       mock_pt_query, mock_pt_update,
                       mock_nc_query, mock_nc_update,
                       mock_rg_query, mock_rg_update):
    """
    End-to-end: create -> fill -> update*3 -> close -> final report.
    Verify: pool status, nav records, trade log, reports.
    """
    # Setup MetricsCalculator mock
    mock_calc = MagicMock()
    mock_calc_cls.return_value = mock_calc
    mock_calc.calculate.return_value = _FAKE_METRICS

    # ---- Phase 1: create_pool ----
    mock_pm_query.return_value = [{'id': POOL_ID}]
    mgr = PoolManager(config=CFG)
    pool_id = mgr.create_pool(
        strategy_id=0, strategy_type='momentum', name='test_lifecycle',
        signal_date=DATE_0, signals_df=_signals_df(),
    )
    assert pool_id == POOL_ID
    assert mock_pm_update.call_count == 1 + N_STOCKS  # 1 pool + N positions

    # ---- Phase 2: fill_entry_prices ----
    mock_pt_query.side_effect = [
        [{'initial_cash': INITIAL_CASH, 'params': CFG_JSON}],   # pool
        [{'id': i+1, 'stock_code': f'60000{i}', 'weight': 0.2} for i in range(N_STOCKS)],  # pending
        [{f'60000{j}': ENTRY_PRICE} for j in range(N_STOCKS)],  # prices (returns dict-like)
    ]
    # Make price lookup work
    def pt_query_side(sql, params, **kw):
        if 'sim_pool' in sql:
            return [{'initial_cash': INITIAL_CASH, 'params': CFG_JSON}]
        if 'sim_position' in sql and 'pending' in sql:
            return [{'id': i+1, 'stock_code': f'60000{i}', 'weight': 0.2} for i in range(N_STOCKS)]
        if 'trade_stock_daily' in sql:
            return [{'stock_code': f'60000{i}', 'close': ENTRY_PRICE} for i in range(N_STOCKS)]
        return []

    mock_pt_query.side_effect = pt_query_side
    tracker = PositionTracker(config=CFG)
    filled = tracker.fill_entry_prices(pool_id=POOL_ID, entry_date=DATE_1)
    assert filled == N_STOCKS

    # ---- Phase 3: update_prices + check_exits (3 days, no exits) ----
    def pt_query_normal(sql, params, **kw):
        if 'sim_pool' in sql:
            return [{'initial_cash': INITIAL_CASH, 'params': CFG_JSON, 'entry_date': DATE_1.isoformat()}]
        if 'sim_position' in sql and 'active' in sql:
            return _active_positions()
        if 'trade_stock_daily' in sql:
            return [{'stock_code': f'60000{i}', 'close': ENTRY_PRICE} for i in range(N_STOCKS)]
        return []

    for d in [DATE_2, DATE_3, DATE_4]:
        mock_pt_query.side_effect = pt_query_normal
        tracker.update_prices(pool_id=POOL_ID, price_date=d)
        exited = tracker.check_exits(pool_id=POOL_ID, price_date=d)
        assert exited == [], f'No exits expected on {d}'

    # ---- Phase 4: close_pool ----
    mock_pm_query.side_effect = [{'status': 'active'}]
    mgr.close_pool(pool_id=POOL_ID, reason='manual')
    assert mock_pm_update.call_count >= 2  # positions + pool update

    # ---- Phase 5: generate_final_report ----
    def rg_query_side(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': INITIAL_CASH}]
        if 'sim_daily_nav' in sql and 'pool_id' in sql and 'benchmark' not in sql:
            return [{'date': DATE_2.isoformat(), 'total_value': 1_010_000},
                    {'date': DATE_3.isoformat(), 'total_value': 1_015_000},
                    {'date': DATE_4.isoformat(), 'total_value': 1_020_000}]
        if 'sim_position' in sql and 'exited' in sql:
            return [_exited_position(i+1, f'60000{i}', f'Stock{i}',
                                     'manual' if i < 3 else 'manual', 0.02 * (1 if i % 2 == 0 else -1))
                    for i in range(N_STOCKS)]
        if 'sim_daily_nav' in sql and 'benchmark' in sql:
            return [{'date': d.isoformat(), 'close': 4200 + i*10} for i, d in enumerate([DATE_2, DATE_3, DATE_4])]
        return []

    mock_rg_query.side_effect = rg_query_side
    reporter = ReportGenerator(config=CFG)
    final = reporter.generate_final_report(pool_id=POOL_ID)

    assert 'position_contributions' in final
    assert 'exit_breakdown' in final
    assert final['total_trades'] == N_STOCKS


# ---------------------------------------------------------------------------
# T5.6b  Stop loss triggers correctly
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_stop_loss_triggers_correctly(mock_query, mock_update):
    """Price drops > 10% => stop_loss exit with correct DB writes."""
    import json
    cfg = SimPoolConfig(stop_loss=-0.10, db_env='local')

    drop_price = ENTRY_PRICE * 0.88  # -12%

    def query_side(sql, params, **kw):
        if 'sim_pool' in sql:
            return [{'initial_cash': INITIAL_CASH, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': DATE_1.isoformat()}]
        if 'sim_position' in sql and 'active' in sql:
            return _active_positions({f'60000{i}': drop_price if i == 0 else ENTRY_PRICE
                                     for i in range(N_STOCKS)})
        return []

    mock_query.side_effect = query_side
    tracker = PositionTracker(config=cfg)
    exited = tracker.check_exits(pool_id=POOL_ID, price_date=DATE_4)

    assert 1 in exited  # stock 600000 hit stop loss

    # Verify trade log was written
    trade_log_calls = [c for c in mock_update.call_args_list
                       if 'sim_trade_log' in c[0][0]]
    assert len(trade_log_calls) >= 1

    # Verify position was updated
    pos_calls = [c for c in mock_update.call_args_list
                 if 'sim_position' in c[0][0] and 'exit_reason' in c[0][0]]
    assert len(pos_calls) == 1
    assert pos_calls[0][0][1][2] == 'stop_loss'


# ---------------------------------------------------------------------------
# T5.6c  Take profit triggers correctly
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_take_profit_triggers_correctly(mock_query, mock_update):
    """Price rises > 20% => take_profit exit."""
    import json
    cfg = SimPoolConfig(take_profit=0.20, db_env='local')
    rise_price = ENTRY_PRICE * 1.22  # +22%

    def query_side(sql, params, **kw):
        if 'sim_pool' in sql:
            return [{'initial_cash': INITIAL_CASH, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': DATE_1.isoformat()}]
        if 'sim_position' in sql and 'active' in sql:
            return _active_positions({f'60000{i}': rise_price if i == 0 else ENTRY_PRICE
                                     for i in range(N_STOCKS)})
        return []

    mock_query.side_effect = query_side
    tracker = PositionTracker(config=cfg)
    exited = tracker.check_exits(pool_id=POOL_ID, price_date=DATE_4)

    assert 1 in exited

    pos_calls = [c for c in mock_update.call_args_list
                 if 'sim_position' in c[0][0] and 'exit_reason' in c[0][0]]
    assert len(pos_calls) == 1
    assert pos_calls[0][0][1][2] == 'take_profit'


# ---------------------------------------------------------------------------
# T5.6d  Max hold triggers on day 61
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.position_tracker.execute_update')
@patch('strategist.sim_pool.position_tracker.execute_query')
def test_max_hold_triggers_on_day_61(mock_query, mock_update):
    """hold_days=61 => exit even if return is positive."""
    import json
    cfg = SimPoolConfig(max_hold_days=60, take_profit=0.99, stop_loss=-0.99, db_env='local')
    entry_61_days_ago = date(2026, 2, 12)
    check_date = date(2026, 4, 14)  # 61 days later

    def query_side(sql, params, **kw):
        if 'sim_pool' in sql:
            return [{'initial_cash': INITIAL_CASH, 'params': json.dumps(cfg.to_dict()),
                     'entry_date': entry_61_days_ago.isoformat()}]
        if 'sim_position' in sql and 'active' in sql:
            positions = _active_positions()
            for p in positions:
                p['entry_date'] = entry_61_days_ago.isoformat()
            return positions
        return []

    mock_query.side_effect = query_side
    tracker = PositionTracker(config=cfg)
    exited = tracker.check_exits(pool_id=POOL_ID, price_date=check_date)

    assert len(exited) == N_STOCKS  # all 5 stocks exceed max_hold

    pos_calls = [c for c in mock_update.call_args_list
                 if 'sim_position' in c[0][0] and 'exit_reason' in c[0][0]]
    assert len(pos_calls) == N_STOCKS
    for c in pos_calls:
        assert c[0][1][2] == 'max_hold'
