# -*- coding: utf-8 -*-
"""
scanner.py + daily_report.py 单元测试

使用 mock 隔离 DB 依赖，测试纯逻辑。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from datetime import date, datetime

import pandas as pd
import numpy as np

from risk_manager.scanner import (
    scan_portfolio,
    scan_watchlist,
    _is_st,
    _load_positions,
    _load_latest_prices,
    _load_ohlcv_history,
    _load_candidate_stocks,
)
from risk_manager.daily_report import generate_risk_report, push_risk_report


# ============================================================
# Helper fixtures
# ============================================================

MOCK_POSITIONS = [
    {'id': 1, 'stock_code': '600519.SH', 'stock_name': '贵州茅台', 'shares': 100, 'cost_price': 1800.0, 'level': 'L1', 'account': 'A'},
    {'id': 2, 'stock_code': '000001.SZ', 'stock_name': '平安银行', 'shares': 1000, 'cost_price': 12.0, 'level': 'L2', 'account': 'A'},
]

MOCK_PRICES = {
    '600519.SH': {'stock_code': '600519.SH', 'close_price': 1850.0, 'open_price': 1840.0, 'high_price': 1860.0, 'low_price': 1830.0, 'volume': 50000, 'trade_date': date(2026, 4, 17)},
    '000001.SZ': {'stock_code': '000001.SZ', 'close_price': 12.5, 'open_price': 12.3, 'high_price': 12.8, 'low_price': 12.1, 'volume': 500000, 'trade_date': date(2026, 4, 17)},
}


def make_mock_ohlcv(n=30, base_price=100.0):
    """Generate mock OHLCV DataFrame."""
    np.random.seed(42)
    dates = pd.bdate_range(start='2026-03-01', periods=n)
    returns = np.random.normal(0.0005, 0.02, n)
    close = base_price * np.cumprod(1 + returns)
    return pd.DataFrame({
        'date': dates,
        'open': close * 0.999,
        'high': close * 1.01,
        'low': close * 0.99,
        'close': close,
        'volume': np.random.randint(100000, 1000000, n).astype(float),
    })


# ============================================================
# _is_st tests
# ============================================================

class TestIsST:
    def test_normal_stock(self):
        assert _is_st('贵州茅台') is False

    def test_st_stock(self):
        assert _is_st('ST华锐') is True

    def test_star_st_stock(self):
        assert _is_st('*ST康得') is True

    def test_empty_name(self):
        assert _is_st('') is False

    def test_none_name(self):
        assert _is_st(None) is False


# ============================================================
# scan_portfolio tests
# ============================================================

class TestScanPortfolio:

    @patch('risk_manager.scanner._query')
    def test_empty_portfolio(self, mock_query):
        """Empty portfolio should return clean result."""
        mock_query.return_value = []
        result = scan_portfolio(user_id=7, env='online')
        assert result['user_id'] == 7
        assert result['portfolio_summary']['total_positions'] == 0
        assert result['stock_alerts'] == []
        assert result['portfolio_alerts'] == []

    @patch('risk_manager.scanner._load_ohlcv_history')
    @patch('risk_manager.scanner._load_latest_prices')
    @patch('risk_manager.scanner._load_positions')
    def test_normal_portfolio(self, mock_pos, mock_prices, mock_ohlcv):
        """Normal portfolio should have summary and possibly some alerts."""
        mock_pos.return_value = MOCK_POSITIONS
        mock_prices.return_value = MOCK_PRICES
        mock_ohlcv.return_value = make_mock_ohlcv(30, 1800)

        result = scan_portfolio(user_id=7, env='online')
        assert result['user_id'] == 7
        summary = result['portfolio_summary']
        assert summary['total_positions'] == 2
        assert summary['total_value'] > 0
        assert summary['l1_count'] == 1
        assert summary['l2_count'] == 1
        assert summary['scan_date'] is not None

    @patch('risk_manager.scanner._load_ohlcv_history')
    @patch('risk_manager.scanner._load_latest_prices')
    @patch('risk_manager.scanner._load_positions')
    def test_concentration_alert(self, mock_pos, mock_prices, mock_ohlcv):
        """High concentration should trigger portfolio alert."""
        # Make one stock dominate (95%+ of portfolio)
        positions = [
            {'id': 1, 'stock_code': '600519.SH', 'stock_name': '贵州茅台', 'shares': 1000, 'cost_price': 1800.0, 'level': 'L1', 'account': 'A'},
            {'id': 2, 'stock_code': '000001.SZ', 'stock_name': '平安银行', 'shares': 100, 'cost_price': 12.0, 'level': 'L2', 'account': 'A'},
        ]
        mock_pos.return_value = positions
        mock_prices.return_value = MOCK_PRICES
        mock_ohlcv.return_value = make_mock_ohlcv(30, 1800)

        result = scan_portfolio(user_id=7, env='online')
        # 600519: 1000*1850=1850000, 000001: 100*12.5=1250
        # 600519 is ~99.9% of portfolio
        assert len(result['portfolio_alerts']) > 0
        assert any('占比' in a or '集中度' in a for a in result['portfolio_alerts'])

    @patch('risk_manager.scanner._load_ohlcv_history')
    @patch('risk_manager.scanner._load_latest_prices')
    @patch('risk_manager.scanner._load_positions')
    def test_st_stock_alert(self, mock_pos, mock_prices, mock_ohlcv):
        """ST stock should trigger alert."""
        positions = [
            {'id': 1, 'stock_code': '600519.SH', 'stock_name': '*ST茅台', 'shares': 100, 'cost_price': 100.0, 'level': 'L1', 'account': 'A'},
        ]
        prices = {
            '600519.SH': {'stock_code': '600519.SH', 'close_price': 100.0, 'open_price': 99.0, 'high_price': 101.0, 'low_price': 98.0, 'volume': 50000, 'trade_date': date(2026, 4, 17)},
        }
        mock_pos.return_value = positions
        mock_prices.return_value = prices
        mock_ohlcv.return_value = make_mock_ohlcv(30, 100)

        result = scan_portfolio(user_id=7, env='online')
        assert len(result['stock_alerts']) > 0
        assert any('ST' in a for alert_group in result['stock_alerts'] for a in alert_group['alerts'])

    @patch('risk_manager.scanner._load_ohlcv_history')
    @patch('risk_manager.scanner._load_latest_prices')
    @patch('risk_manager.scanner._load_positions')
    def test_missing_price_data(self, mock_pos, mock_prices, mock_ohlcv):
        """Stock with no price data should get a warning."""
        positions = [
            {'id': 1, 'stock_code': '999999.SH', 'stock_name': '未知股', 'shares': 100, 'cost_price': 10.0, 'level': 'L2', 'account': 'A'},
        ]
        mock_pos.return_value = positions
        mock_prices.return_value = {}  # no prices
        mock_ohlcv.return_value = None

        result = scan_portfolio(user_id=7, env='online')
        assert len(result['stock_alerts']) == 1
        assert '无法获取' in result['stock_alerts'][0]['alerts'][0]


# ============================================================
# scan_watchlist tests
# ============================================================

class TestScanWatchlist:

    @patch('risk_manager.scanner._query')
    def test_empty_watchlist(self, mock_query):
        """Empty candidate pool."""
        mock_query.return_value = []
        result = scan_watchlist(env='online')
        assert result['total'] == 0
        assert result['alerts'] == []

    @patch('risk_manager.scanner._load_ohlcv_history')
    @patch('risk_manager.scanner._load_latest_prices')
    @patch('risk_manager.scanner._load_candidate_stocks')
    def test_normal_watchlist(self, mock_cands, mock_prices, mock_ohlcv):
        """Normal candidates with prices."""
        mock_cands.return_value = [
            {'stock_code': '600519.SH', 'stock_name': '贵州茅台'},
        ]
        mock_prices.return_value = {
            '600519.SH': {'stock_code': '600519.SH', 'close_price': 1850.0, 'open_price': 1840.0, 'high_price': 1860.0, 'low_price': 1830.0, 'volume': 50000, 'trade_date': date(2026, 4, 17)},
        }
        mock_ohlcv.return_value = make_mock_ohlcv(30, 1800)

        result = scan_watchlist(env='online')
        assert result['total'] == 1


# ============================================================
# generate_risk_report tests
# ============================================================

class TestGenerateReport:

    @patch('risk_manager.scanner._load_ohlcv_history')
    @patch('risk_manager.scanner._load_latest_prices')
    @patch('risk_manager.scanner._load_positions')
    def test_report_format(self, mock_pos, mock_prices, mock_ohlcv):
        """Report should be valid Markdown."""
        mock_pos.return_value = MOCK_POSITIONS
        mock_prices.return_value = MOCK_PRICES
        mock_ohlcv.return_value = make_mock_ohlcv(30, 1800)

        report = generate_risk_report(user_id=7, env='online')
        assert '# 持仓风控日报' in report
        assert '## 组合概览' in report
        assert '持仓数量: 2' in report

    @patch('risk_manager.scanner._query')
    def test_empty_portfolio_report(self, mock_query):
        """Empty portfolio should still generate a report."""
        mock_query.return_value = []
        report = generate_risk_report(user_id=7, env='online')
        assert '# 持仓风控日报' in report
        assert '持仓数量: 0' in report


# ============================================================
# push_risk_report tests
# ============================================================

class TestPushReport:

    @patch('risk_manager.scanner._query')
    def test_push_creates_inbox_message(self, mock_query):
        """push_risk_report should call create_message."""
        mock_query.return_value = []

        mock_create = MagicMock(return_value=42)
        # Patch the lazy import target
        with patch.dict('sys.modules', {'api': MagicMock(), 'api.services': MagicMock(), 'api.services.inbox_service': MagicMock(create_message=mock_create)}):
            msg_id = push_risk_report(user_id=7, env='online')

        assert msg_id == 42
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[1]['user_id'] == 7 or call_args[0][0] == 7


# ============================================================
# RiskContext correlation_matrix field test
# ============================================================

class TestRiskContextCorrelation:
    def test_correlation_matrix_default_none(self):
        from risk_manager.models import RiskContext
        ctx = RiskContext(stock_code='600519.SH', price=100.0)
        assert ctx.correlation_matrix is None

    def test_correlation_matrix_with_value(self):
        from risk_manager.models import RiskContext
        corr = pd.DataFrame({'A': [1.0, 0.5], 'B': [0.5, 1.0]}, index=['A', 'B'])
        ctx = RiskContext(stock_code='600519.SH', price=100.0, correlation_matrix=corr)
        assert ctx.correlation_matrix is not None
        assert ctx.correlation_matrix.shape == (2, 2)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
