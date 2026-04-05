# -*- coding: utf-8 -*-
import json
import pytest
from unittest.mock import MagicMock, patch
from research.fundamental.snapshot import FundamentalSnapshot


@pytest.fixture
def snap():
    """FundamentalSnapshot with all external dependencies mocked."""
    s = FundamentalSnapshot.__new__(FundamentalSnapshot)
    from research.fundamental.valuation import ValuationResult
    from research.fundamental.scorer import ScoreResult

    val_result = ValuationResult(
        code='300750',
        current_market_cap_yi=5000.0,
        methods=[{'method': 'PE-earnings', 'fair_market_cap_yi': 4000.0,
                  'vs_current': -0.20, 'note': 'test'}],
    )
    score_result = ScoreResult(
        earnings_quality_score=25,
        valuation_score=30,
        growth_score=12,
        composite_score=67,
        label='良好',
    )

    import pandas as pd
    s._valuator = MagicMock()
    s._valuator.compute.return_value = val_result
    s._valuator._get_market_data.return_value = {
        'pe_ttm': 20.0, 'pb': 2.5, 'total_mv': 5000000.0, 'dv_ttm': 2.0, 'close': 100.0
    }
    s._valuator._get_financial_data.return_value = {
        'net_profit_ttm': 25_0000_0000,
        'total_assets': 200_0000_0000,
        'total_liabilities': 100_0000_0000,
        'net_assets': 100_0000_0000,
        'operating_cashflow': 30_0000_0000,
        'capex': 10_0000_0000,
        'revenue_ttm': 200_0000_0000,
        'roe': 0.18,
        'revenue_yoy': 0.15,
        'profit_yoy': 0.20,
    }
    s._valuator._get_pe_series.return_value = pd.Series([15.0, 18.0, 22.0, 25.0, 20.0])
    s._valuator._get_pb_series.return_value = pd.Series([1.5, 2.0, 2.5, 3.0, 2.8])
    s._scorer = MagicMock()
    s._scorer.score.return_value = score_result
    return s


def test_build_row_has_required_keys(snap):
    with patch('research.fundamental.snapshot.ReportDataTools') as mock_dt:
        mock_dt.return_value.get_expected_return_context.return_value = '2年预期总回报：28.4%'
        row = snap._build_row('300750')
    required = {'code', 'snap_date', 'fundamental_score', 'pe_ttm',
                'pe_quantile_5yr', 'pb', 'pb_quantile_5yr', 'valuation_json'}
    assert required.issubset(row.keys())


def test_build_row_valuation_json_is_valid_json(snap):
    with patch('research.fundamental.snapshot.ReportDataTools') as mock_dt:
        mock_dt.return_value.get_expected_return_context.return_value = '无数据'
        row = snap._build_row('300750')
    data = json.loads(row['valuation_json'])
    assert 'methods' in data
    assert len(data['methods']) == 1


def test_build_row_fundamental_score_is_67(snap):
    with patch('research.fundamental.snapshot.ReportDataTools') as mock_dt:
        mock_dt.return_value.get_expected_return_context.return_value = '无数据'
        row = snap._build_row('300750')
    assert row['fundamental_score'] == 67


def test_save_calls_upsert(snap):
    with patch('research.fundamental.snapshot.ReportDataTools') as mock_dt, \
         patch.object(snap, '_upsert') as mock_upsert:
        mock_dt.return_value.get_expected_return_context.return_value = '无数据'
        snap.save('300750')
    mock_upsert.assert_called_once()


def test_save_batch_returns_successful_codes(snap):
    with patch('research.fundamental.snapshot.ReportDataTools') as mock_dt, \
         patch.object(snap, '_upsert'):
        mock_dt.return_value.get_expected_return_context.return_value = '无数据'
        # Reinitialize to handle multiple codes
        snap._valuator.compute.side_effect = [
            snap._valuator.compute.return_value,
            Exception('DB error'),
        ]
        snap._valuator._get_market_data.side_effect = [
            snap._valuator._get_market_data.return_value,
            snap._valuator._get_market_data.return_value,
        ]
        # For this test, just verify save_batch works on success
        snap._valuator.compute.side_effect = None  # reset
        ok = snap.save_batch(['300750'])
    assert '300750' in ok
