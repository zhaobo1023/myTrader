# -*- coding: utf-8 -*-
"""
Hard-tech factor definitions and parameters

Factor groups:
  Innovation (25%): rd_intensity, rd_growth, rd_efficiency
  Growth (25%):     revenue_growth, gross_margin_trend
  Quality (20%):    roe_ttm, gross_margin
  Technical (15%):  mom_20
  Valuation (15%):  market_cap
"""

# Hard-tech specific factors (from trade_stock_hardtech_factor)
HARDTECH_FACTOR_DEFS = [
    {
        'name': 'rd_intensity',
        'table': 'trade_stock_hardtech_factor',
        'column': 'rd_intensity',
        'direction': 1,
        'label': 'R&D Intensity',
    },
    {
        'name': 'rd_growth',
        'table': 'trade_stock_hardtech_factor',
        'column': 'rd_growth',
        'direction': 1,
        'label': 'R&D Growth YoY',
    },
    {
        'name': 'rd_efficiency',
        'table': 'trade_stock_hardtech_factor',
        'column': 'rd_efficiency',
        'direction': 1,
        'label': 'R&D Efficiency',
    },
    {
        'name': 'gross_margin_trend',
        'table': 'trade_stock_hardtech_factor',
        'column': 'gross_margin_trend',
        'direction': 1,
        'label': 'Gross Margin Trend',
    },
]

# Reused factors from existing factor tables
REUSED_FACTOR_DEFS = [
    {
        'name': 'revenue_growth',
        'table': 'trade_stock_extended_factor',
        'column': 'revenue_growth',
        'direction': 1,
        'label': 'Revenue Growth',
    },
    {
        'name': 'gross_margin',
        'table': 'trade_stock_extended_factor',
        'column': 'gross_margin',
        'direction': 1,
        'label': 'Gross Margin',
    },
    {
        'name': 'roe_ttm',
        'table': 'trade_stock_extended_factor',
        'column': 'roe_ttm',
        'direction': 1,
        'label': 'ROE TTM',
    },
    {
        'name': 'mom_20',
        'table': 'trade_stock_basic_factor',
        'column': 'mom_20',
        'direction': 1,
        'label': 'Momentum 20D',
    },
    {
        'name': 'market_cap',
        'table': 'trade_stock_valuation_factor',
        'column': 'market_cap',
        'direction': -1,
        'label': 'Small Cap',
    },
]

ALL_FACTOR_DEFS = HARDTECH_FACTOR_DEFS + REUSED_FACTOR_DEFS

# Factor direction mapping
FACTOR_DIRECTIONS = {f['name']: f['direction'] for f in ALL_FACTOR_DEFS}

# Factor labels
FACTOR_LABELS = {f['name']: f['label'] for f in ALL_FACTOR_DEFS}

# Factor name list
HARDTECH_FACTORS = [f['name'] for f in ALL_FACTOR_DEFS]

# Five-group factor structure
FACTOR_GROUPS = [
    {
        'name': 'innovation',
        'label': 'Innovation',
        'factors': ['rd_intensity', 'rd_growth', 'rd_efficiency'],
        'weight': 0.25,
    },
    {
        'name': 'growth',
        'label': 'Growth',
        'factors': ['revenue_growth', 'gross_margin_trend'],
        'weight': 0.25,
    },
    {
        'name': 'quality',
        'label': 'Quality',
        'factors': ['roe_ttm', 'gross_margin'],
        'weight': 0.20,
    },
    {
        'name': 'technical',
        'label': 'Technical',
        'factors': ['mom_20'],
        'weight': 0.15,
    },
    {
        'name': 'valuation',
        'label': 'Valuation',
        'factors': ['market_cap'],
        'weight': 0.15,
    },
]

# IC validation parameters
IC_FORWARD_PERIOD = 20
IC_MIN_SAMPLES = 30
IC_MIN_DATES = 20
