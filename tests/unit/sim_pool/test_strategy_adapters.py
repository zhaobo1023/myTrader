# -*- coding: utf-8 -*-
"""T5.5 Unit tests for strategy adapters."""

import json
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from strategist.sim_pool.strategies.base import BaseStrategyAdapter


# ---------------------------------------------------------------------------
# T5.5a  BaseStrategyAdapter is abstract
# ---------------------------------------------------------------------------

def test_base_adapter_is_abstract():
    """Cannot instantiate BaseStrategyAdapter directly."""
    with pytest.raises(TypeError):
        BaseStrategyAdapter()


# ---------------------------------------------------------------------------
# T5.5b  MomentumAdapter returns DataFrame
# ---------------------------------------------------------------------------

@patch('strategist.doctor_tao.signal_screener.SignalScreener')
def test_momentum_adapter_returns_dataframe(mock_screener_cls):
    """MomentumAdapter.run() returns DataFrame with stock_code/stock_name."""
    mock_screener = MagicMock()
    mock_screener_cls.return_value = mock_screener
    mock_screener.run_screener.return_value = pd.DataFrame({
        'stock_code': ['000001', '000002'],
        'stock_name': ['StockA', 'StockB'],
        'signal_type': ['momentum', 'momentum'],
        'rps': [95, 88],
    })

    from strategist.sim_pool.strategies.momentum import MomentumAdapter
    adapter = MomentumAdapter()
    result = adapter.run(signal_date='2026-04-14', params={})

    assert isinstance(result, pd.DataFrame)
    assert 'stock_code' in result.columns
    assert 'stock_name' in result.columns
    assert len(result) == 2


# ---------------------------------------------------------------------------
# T5.5c  MomentumAdapter signal_meta is serializable
# ---------------------------------------------------------------------------

@patch('strategist.doctor_tao.signal_screener.SignalScreener')
def test_adapter_signal_meta_is_serializable(mock_screener_cls):
    """signal_meta column can be json.dumps serialized."""
    mock_screener = MagicMock()
    mock_screener_cls.return_value = mock_screener
    mock_screener.run_screener.return_value = pd.DataFrame({
        'stock_code': ['000001'],
        'stock_name': ['StockA'],
        'signal_type': ['momentum'],
        'rps': [95],
        'ma20': [10.5],
    })

    from strategist.sim_pool.strategies.momentum import MomentumAdapter
    adapter = MomentumAdapter()
    result = adapter.run(signal_date='2026-04-14', params={})

    assert 'signal_meta' in result.columns
    for val in result['signal_meta']:
        parsed = json.loads(val)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# T5.5d  IndustryAdapter filters by industry
# ---------------------------------------------------------------------------

@patch('strategist.universe_scanner.scoring_engine.ScoringEngine')
def test_industry_adapter_filters_by_industry(mock_engine_cls):
    """industry_names=['bank'] returns only bank stocks."""
    mock_engine = MagicMock()
    mock_engine_cls.return_value = mock_engine
    mock_engine.run.return_value = pd.DataFrame({
        'code': ['000001', '600036', '601398'],
        'name': ['StockA', 'StockB', 'StockC'],
        'tier': ['high_priority', 'high_priority', 'high_priority'],
        'industry': ['tech', 'bank', 'bank'],
        'total_score': [80, 90, 85],
    })

    from strategist.sim_pool.strategies.industry import IndustryAdapter
    adapter = IndustryAdapter()
    result = adapter.run(signal_date='2026-04-14', params={'industry_names': ['bank']})

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    assert all('bank' in str(meta) for meta in result['signal_meta'])


# ---------------------------------------------------------------------------
# T5.5e  MicroCapAdapter market cap filter
# ---------------------------------------------------------------------------

@patch('strategist.sim_pool.strategies.micro_cap.execute_query')
def test_micro_cap_adapter_market_cap_filter(mock_query):
    """All returned stocks should pass the market cap filter."""
    # First call: basic data (circ_mv < threshold)
    mock_query.side_effect = [
        # basic data
        [
            {'stock_code': '000001', 'stock_name': 'SmallA', 'circ_mv': 30e8,
             'close': 5.0, 'pe_ttm': 20, 'pb': 1.5},
        ],
        # daily data
        [
            {'stock_code': '000001', 'avg_amount_60d': 20000000,
             'close_today': 5.0, 'ma20_approx': 4.8},
        ],
    ]

    from strategist.sim_pool.strategies.micro_cap import MicroCapAdapter
    adapter = MicroCapAdapter()
    result = adapter.run(signal_date='2026-04-14', params={'max_circ_mv': 50, 'min_amt_60d': 1000})

    assert isinstance(result, pd.DataFrame)
    if not result.empty:
        for _, row in result.iterrows():
            meta = json.loads(row['signal_meta'])
            assert meta.get('circ_mv', 999e8) < 50e8, f'Stock {row["stock_code"]} exceeds market cap limit'
