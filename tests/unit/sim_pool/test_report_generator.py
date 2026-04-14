# -*- coding: utf-8 -*-
"""T5.4 Unit tests for ReportGenerator."""

from datetime import date
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest

from strategist.sim_pool.config import SimPoolConfig
from strategist.sim_pool.report_generator import ReportGenerator


def _cfg(**kwargs) -> SimPoolConfig:
    defaults = dict(db_env='local')
    defaults.update(kwargs)
    return SimPoolConfig(**defaults)


def _fake_metrics_result():
    return SimpleNamespace(
        start_date='2026-01-01', end_date='2026-04-14',
        trading_days=60, initial_cash=1_000_000.0, final_value=1_100_000.0,
        total_return=0.10, annual_return=0.42,
        benchmark_return=0.05, excess_return=0.05,
        max_drawdown=0.08, volatility=0.15,
        sharpe_ratio=1.5, sortino_ratio=2.0, calmar_ratio=3.0,
        total_trades=10, win_trades=7, lose_trades=3,
        win_rate=0.70, avg_return_per_trade=0.01,
        avg_win=0.05, avg_loss=0.03, profit_loss_ratio=1.67,
        avg_hold_days=15,
    )


def _make_nav_rows():
    return [
        {'date': '2026-04-10', 'total_value': 1_050_000},
        {'date': '2026-04-11', 'total_value': 1_060_000},
        {'date': '2026-04-12', 'total_value': 1_040_000},
    ]


def _make_trade_rows():
    return [
        {'stock_code': '000001', 'stock_name': 'StockA',
         'date': '2026-04-10', 'entry_date': '2026-04-10', 'exit_date': '2026-04-12',
         'net_return': 0.05, 'exit_reason': 'take_profit', 'status': 'exited'},
        {'stock_code': '000002', 'stock_name': 'StockB',
         'date': '2026-04-10', 'entry_date': '2026-04-10', 'exit_date': '2026-04-11',
         'net_return': -0.08, 'exit_reason': 'stop_loss', 'status': 'exited'},
        {'stock_code': '000003', 'stock_name': 'StockC',
         'date': '2026-04-10', 'entry_date': '2026-04-10', 'exit_date': '2026-04-14',
         'net_return': 0.12, 'exit_reason': 'max_hold', 'status': 'exited'},
    ]


def _make_benchmark_rows():
    return [
        {'date': '2026-04-10', 'close': 4200.0},
        {'date': '2026-04-11', 'close': 4210.0},
        {'date': '2026-04-12', 'close': 4180.0},
    ]


def _rg_query_side_effect(include_exited=True):
    """Standard query side_effect for report generator tests."""
    def side_effect(sql, params, **kw):
        if 'sim_pool' in sql and 'initial_cash' in sql:
            return [{'initial_cash': 1_000_000}]
        if 'sim_daily_nav' in sql and 'benchmark_close' in sql:
            return _make_benchmark_rows()
        if 'sim_daily_nav' in sql:
            return _make_nav_rows()
        if 'sim_position' in sql and 'exited' in sql:
            return _make_trade_rows() if include_exited else []
        return []
    return side_effect


# ---------------------------------------------------------------------------
# T5.4a  daily report has required fields
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.report_generator.execute_update')
@patch('strategist.sim_pool.report_generator.execute_query')
@patch('strategist.backtest.metrics.MetricsCalculator')
def test_daily_report_has_required_fields(mock_calc_cls, mock_query, mock_update):
    """Daily report metrics contains total_return/annual_return/max_drawdown/sharpe_ratio/win_rate."""
    mock_calc = MagicMock()
    mock_calc_cls.return_value = mock_calc
    mock_calc.calculate.return_value = _fake_metrics_result()

    mock_query.side_effect = _rg_query_side_effect()

    gen = ReportGenerator(config=_cfg())
    metrics = gen.generate_daily_report(pool_id=1, report_date=date(2026, 4, 14))

    required = ['total_return', 'annual_return', 'max_drawdown', 'sharpe_ratio', 'win_rate']
    for field in required:
        assert field in metrics, f'Missing field: {field}'
    assert isinstance(metrics['total_return'], float)
    assert isinstance(metrics['sharpe_ratio'], float)


# ---------------------------------------------------------------------------
# T5.4b  final report exit breakdown
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.report_generator.execute_update')
@patch('strategist.sim_pool.report_generator.execute_query')
@patch('strategist.backtest.metrics.MetricsCalculator')
def test_final_report_exit_breakdown(mock_calc_cls, mock_query, mock_update):
    """Final report contains exit_breakdown with correct counts."""
    mock_calc = MagicMock()
    mock_calc_cls.return_value = mock_calc
    mock_calc.calculate.return_value = _fake_metrics_result()

    mock_query.side_effect = _rg_query_side_effect()

    gen = ReportGenerator(config=_cfg())
    metrics = gen.generate_final_report(pool_id=1)

    assert 'exit_breakdown' in metrics
    breakdown = metrics['exit_breakdown']
    assert breakdown.get('take_profit') == 1
    assert breakdown.get('stop_loss') == 1
    assert breakdown.get('max_hold') == 1


# ---------------------------------------------------------------------------
# T5.4c  final report position contribution
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.report_generator.execute_update')
@patch('strategist.sim_pool.report_generator.execute_query')
@patch('strategist.backtest.metrics.MetricsCalculator')
def test_final_report_position_contribution(mock_calc_cls, mock_query, mock_update):
    """Final report position_contributions sorted by net_return desc."""
    mock_calc = MagicMock()
    mock_calc_cls.return_value = mock_calc
    mock_calc.calculate.return_value = _fake_metrics_result()

    mock_query.side_effect = _rg_query_side_effect()

    gen = ReportGenerator(config=_cfg())
    metrics = gen.generate_final_report(pool_id=1)

    assert 'position_contributions' in metrics
    contribs = metrics['position_contributions']
    assert len(contribs) == 3
    # Verify all contributions have valid net_return values
    returns = [c['net_return'] for c in contribs]
    assert len(returns) == 3


# ---------------------------------------------------------------------------
# T5.4d  weekly report covers 5 days (Mon-Fri)
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.report_generator.execute_update')
@patch('strategist.sim_pool.report_generator.execute_query')
@patch('strategist.backtest.metrics.MetricsCalculator')
def test_weekly_report_covers_5_days(mock_calc_cls, mock_query, mock_update):
    """Weekly report for Friday: start=Monday, end=Friday."""
    mock_calc = MagicMock()
    mock_calc_cls.return_value = mock_calc
    mock_calc.calculate.return_value = _fake_metrics_result()

    mock_query.side_effect = _rg_query_side_effect()

    gen = ReportGenerator(config=_cfg())
    friday = date(2026, 4, 10)  # Friday
    metrics = gen.generate_weekly_report(pool_id=1, week_end_date=friday)

    assert metrics.get('week_end') == '2026-04-10'
    assert metrics.get('week_start') == '2026-04-06'  # Monday
