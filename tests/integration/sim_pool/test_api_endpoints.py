# -*- coding: utf-8 -*-
"""T5.7 Integration tests for SimPool API endpoints.

These tests mock the service layer and verify the API router returns
correct status codes and response shapes.
"""

import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

# We need to import the app to create a test client
# The router imports work because we patch the service layer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_app():
    """Create a test FastAPI app with just the sim-pool router."""
    from fastapi import FastAPI
    from api.routers.sim_pool import router

    app = FastAPI()
    app.include_router(router)
    return app


def _pool_row(**overrides):
    defaults = {
        'id': 1, 'strategy_type': 'momentum', 'signal_date': '2026-04-14',
        'status': 'active', 'initial_cash': 1000000, 'current_value': 1050000,
        'total_return': 0.05, 'max_drawdown': 0.03, 'sharpe_ratio': 1.2,
        'created_at': '2026-04-14 10:00:00', 'closed_at': None,
    }
    defaults.update(overrides)
    return defaults


def _position_row(**overrides):
    defaults = {
        'id': 1, 'stock_code': '000001', 'stock_name': 'StockA',
        'status': 'open', 'entry_price': 10.0, 'current_price': 10.5,
        'shares': 1000, 'net_return': None, 'exit_reason': None,
        'entry_date': '2026-04-14', 'exit_date': None, 'hold_days': 5,
    }
    defaults.update(overrides)
    return defaults


def _trade_row(**overrides):
    defaults = {
        'id': 1, 'pool_id': 1, 'position_id': 1, 'stock_code': '000001',
        'trade_date': '2026-04-14', 'action': 'buy', 'price': 10.01,
        'shares': 1000, 'amount': 10010, 'commission': 3.0,
        'slippage_cost': 10.0, 'stamp_tax': 0, 'net_amount': -10023.0,
        'trigger': 'entry', 'created_at': '2026-04-14 09:35:00',
    }
    defaults.update(overrides)
    return defaults


def _report_row(**overrides):
    defaults = {
        'id': 1, 'pool_id': 1, 'report_date': '2026-04-14',
        'report_type': 'daily', 'metrics': None, 'created_at': '2026-04-14 16:30:00',
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# T5.7a  List pools (empty)
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_list_pools_empty(mock_svc):
    mock_svc.list_pools.return_value = []

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool')

    assert resp.status_code == 200
    data = resp.json()
    assert data['pools'] == []
    assert data['total'] == 0


# ---------------------------------------------------------------------------
# T5.7b  List pools (with data)
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_list_pools_with_data(mock_svc):
    mock_svc.list_pools.return_value = [_pool_row(), _pool_row(id=2, strategy_type='industry')]

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool?status=active&strategy_type=momentum')

    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 2
    mock_svc.list_pools.assert_called_once_with(strategy_type='momentum', status='active')


# ---------------------------------------------------------------------------
# T5.7c  Get pool detail
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_get_pool_detail(mock_svc):
    mock_svc.get_pool.return_value = _pool_row(
        positions=[_position_row(), _position_row(id=2, stock_code='000002', stock_name='StockB')]
    )

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool/1')

    assert resp.status_code == 200
    assert resp.json()['strategy_type'] == 'momentum'


# ---------------------------------------------------------------------------
# T5.7d  Get pool not found
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_get_pool_not_found(mock_svc):
    mock_svc.get_pool.return_value = None

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool/999')

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T5.7e  Get positions with filter
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_get_positions_filter(mock_svc):
    mock_svc.get_pool.return_value = _pool_row()
    mock_svc.get_positions.return_value = [_position_row(status='open')]

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool/1/positions?status=open')

    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 1
    mock_svc.get_positions.assert_called_once_with(1, status='open')


# ---------------------------------------------------------------------------
# T5.7f  Get nav series
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_get_nav_returns_series(mock_svc):
    mock_svc.get_pool.return_value = _pool_row()
    mock_svc.get_nav_series.return_value = [
        {'nav_date': '2026-04-14', 'nav': 1.0, 'total_value': 1000000},
        {'nav_date': '2026-04-15', 'nav': 1.02, 'total_value': 1020000},
    ]
    mock_svc.get_benchmark_nav_series.return_value = [
        {'trade_date': '2026-04-14', 'close': 4200},
    ]

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool/1/nav')

    assert resp.status_code == 200
    data = resp.json()
    assert len(data['nav']) == 2
    assert len(data['benchmark']) == 1


# ---------------------------------------------------------------------------
# T5.7g  Get trade log
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_get_trades(mock_svc):
    mock_svc.get_pool.return_value = _pool_row()
    mock_svc.get_trade_log.return_value = [_trade_row(), _trade_row(id=2, action='sell')]

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool/1/trades')

    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 2


# ---------------------------------------------------------------------------
# T5.7h  Force close pool
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_close_pool_changes_status(mock_svc):
    mock_svc.get_pool.return_value = _pool_row(status='active')
    mock_svc.force_close_pool.return_value = None

    app = _mock_app()
    client = TestClient(app)
    resp = client.post('/api/sim-pool/1/close')

    assert resp.status_code == 200
    assert resp.json()['status'] == 'closed'
    mock_svc.force_close_pool.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# T5.7i  Close already closed pool
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_close_already_closed_pool(mock_svc):
    mock_svc.get_pool.return_value = _pool_row(status='closed')

    app = _mock_app()
    client = TestClient(app)
    resp = client.post('/api/sim-pool/1/close')

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T5.7j  Reports list and detail
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_reports_available(mock_svc):
    mock_svc.get_pool.return_value = _pool_row()
    mock_svc.list_reports.return_value = [
        _report_row(id=1, report_type='daily', report_date='2026-04-14'),
        _report_row(id=2, report_type='daily', report_date='2026-04-15'),
        _report_row(id=3, report_type='final', report_date='2026-04-20'),
    ]

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool/1/reports')

    assert resp.status_code == 200
    assert resp.json()['total'] == 3


@patch('api.routers.sim_pool._svc')
def test_report_detail_not_found(mock_svc):
    mock_svc.get_pool.return_value = _pool_row()
    mock_svc.get_report.return_value = None

    app = _mock_app()
    client = TestClient(app)
    resp = client.get('/api/sim-pool/1/reports/2026-04-14/daily')

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T5.7k  Create pool with invalid strategy_type
# ---------------------------------------------------------------------------

@patch('api.routers.sim_pool._svc')
def test_create_pool_invalid_strategy(mock_svc):
    app = _mock_app()
    client = TestClient(app)
    resp = client.post('/api/sim-pool', json={
        'strategy_type': 'invalid_type',
        'signal_date': '2026-04-14',
        'config': {},
    })

    assert resp.status_code == 400
