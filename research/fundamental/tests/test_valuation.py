# -*- coding: utf-8 -*-
import pytest
import pandas as pd
from unittest.mock import MagicMock
from research.fundamental.valuation import FundamentalValuator, ValuationResult


@pytest.fixture
def mock_market():
    return {'pe_ttm': 20.0, 'pb': 2.5, 'total_mv': 5000000.0, 'dv_ttm': 2.0, 'close': 100.0}

@pytest.fixture
def mock_financials():
    return {
        'net_profit_ttm': 25_0000_0000,    # 25 yi
        'total_assets': 200_0000_0000,
        'total_liabilities': 100_0000_0000,
        'net_assets': 100_0000_0000,
        'operating_cashflow': 30_0000_0000,
        'capex': 10_0000_0000,
        'revenue_ttm': 200_0000_0000,
    }

@pytest.fixture
def mock_pe_series():
    return pd.Series([15.0, 18.0, 22.0, 25.0, 30.0, 20.0, 17.0])

@pytest.fixture
def mock_pb_series():
    return pd.Series([1.5, 2.0, 2.5, 3.0, 3.5, 2.8, 2.2])


def _make_valuator(mock_market, mock_financials, mock_pe_series, mock_pb_series):
    v = FundamentalValuator.__new__(FundamentalValuator)
    v._get_market_data = MagicMock(return_value=mock_market)
    v._get_financial_data = MagicMock(return_value=mock_financials)
    v._get_pe_series = MagicMock(return_value=mock_pe_series)
    v._get_pb_series = MagicMock(return_value=mock_pb_series)
    return v


def test_result_has_8_methods(mock_market, mock_financials, mock_pe_series, mock_pb_series):
    v = _make_valuator(mock_market, mock_financials, mock_pe_series, mock_pb_series)
    result = v.compute('300750')
    assert len(result.methods) == 8
    names = [m['method'] for m in result.methods]
    for expected in ('PE-earnings', 'PB-netasset', 'FCF-yield', 'DCF-3stage',
                     'Gordon-implied-g', 'Ceiling-matrix', 'Liquidation', 'Replacement'):
        assert expected in names


def test_pe_earnings_uses_40th_percentile(mock_market, mock_financials, mock_pe_series, mock_pb_series):
    v = _make_valuator(mock_market, mock_financials, mock_pe_series, mock_pb_series)
    result = v.compute('300750')
    pe_method = next(m for m in result.methods if m['method'] == 'PE-earnings')
    assert pe_method['fair_market_cap_yi'] > 0
    # fair_pe should be 40th pct of [15,17,18,20,22,25,30] ~ 18.4
    assert 15 < pe_method['fair_pe'] < 22


def test_gordon_implied_g_formula(mock_market, mock_financials, mock_pe_series, mock_pb_series):
    v = _make_valuator(mock_market, mock_financials, mock_pe_series, mock_pb_series)
    result = v.compute('300750')
    gordon = next(m for m in result.methods if m['method'] == 'Gordon-implied-g')
    # PE=20, cost_of_equity=8%: implied_g = 8% - 1/20 = 3%
    assert abs(gordon['implied_growth_rate'] - 0.03) < 0.001
    assert gordon['fair_market_cap_yi'] is None   # diagnostic only


def test_ceiling_matrix_has_9_scenarios(mock_market, mock_financials, mock_pe_series, mock_pb_series):
    v = _make_valuator(mock_market, mock_financials, mock_pe_series, mock_pb_series)
    result = v.compute('300750')
    ceiling = next(m for m in result.methods if m['method'] == 'Ceiling-matrix')
    assert len(ceiling['scenarios']) == 9


def test_missing_financials_returns_none_for_financial_methods(mock_market, mock_pe_series, mock_pb_series):
    v = FundamentalValuator.__new__(FundamentalValuator)
    v._get_market_data = MagicMock(return_value=mock_market)
    v._get_financial_data = MagicMock(return_value=None)
    v._get_pe_series = MagicMock(return_value=mock_pe_series)
    v._get_pb_series = MagicMock(return_value=mock_pb_series)
    result = v.compute('000001')
    fcf = next(m for m in result.methods if m['method'] == 'FCF-yield')
    liq = next(m for m in result.methods if m['method'] == 'Liquidation')
    assert fcf['fair_market_cap_yi'] is None
    assert liq['fair_market_cap_yi'] is None


def test_to_tushare_conversion():
    from research.fundamental.valuation import _to_tushare
    assert _to_tushare('300750') == '300750.SZ'
    assert _to_tushare('600519') == '600519.SH'
    assert _to_tushare('000001') == '000001.SZ'
    assert _to_tushare('600519.SH') == '600519.SH'
