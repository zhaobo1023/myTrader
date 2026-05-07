# -*- coding: utf-8 -*-
"""
Hard-tech factor definitions and parameters

Factor groups:
  Innovation (30%): rd_intensity, rd_growth, rd_efficiency, gross_margin_trend
  Quality (30%):    gross_margin, revenue_growth, net_profit_growth
  Momentum (25%):   rps_250, mom_20
  Valuation (15%):  pe_ttm
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
        'name': 'gross_margin',
        'table': 'trade_stock_extended_factor',
        'column': 'gross_margin',
        'direction': 1,
        'label': 'Gross Margin',
    },
    {
        'name': 'revenue_growth',
        'table': 'trade_stock_extended_factor',
        'column': 'revenue_growth',
        'direction': 1,
        'label': 'Revenue Growth',
    },
    {
        'name': 'net_profit_growth',
        'table': 'trade_stock_extended_factor',
        'column': 'net_profit_growth',
        'direction': 1,
        'label': 'Net Profit Growth',
    },
    {
        'name': 'rps_250',
        'table': 'trade_stock_rps',
        'column': 'rps_250',
        'direction': 1,
        'label': 'RPS 250D',
    },
    {
        'name': 'mom_20',
        'table': 'trade_stock_basic_factor',
        'column': 'mom_20',
        'direction': 1,
        'label': 'Momentum 20D',
    },
    {
        'name': 'pe_ttm',
        'table': 'trade_stock_valuation_factor',
        'column': 'pe_ttm',
        'direction': -1,
        'label': 'PE TTM',
    },
]

ALL_FACTOR_DEFS = HARDTECH_FACTOR_DEFS + REUSED_FACTOR_DEFS

# Factor direction mapping
FACTOR_DIRECTIONS = {f['name']: f['direction'] for f in ALL_FACTOR_DEFS}

# Factor labels
FACTOR_LABELS = {f['name']: f['label'] for f in ALL_FACTOR_DEFS}

# Factor name list
HARDTECH_FACTORS = [f['name'] for f in ALL_FACTOR_DEFS]

# Factor group structure
FACTOR_GROUPS = [
    {
        'name': 'innovation',
        'label': 'Innovation',
        'factors': ['rd_intensity', 'rd_growth', 'rd_efficiency', 'gross_margin_trend'],
        'weight': 0.30,
    },
    {
        'name': 'quality',
        'label': 'Quality',
        'factors': ['gross_margin', 'revenue_growth', 'net_profit_growth'],
        'weight': 0.30,
    },
    {
        'name': 'momentum',
        'label': 'Momentum',
        'factors': ['rps_250', 'mom_20'],
        'weight': 0.25,
    },
    {
        'name': 'valuation',
        'label': 'Valuation',
        'factors': ['pe_ttm'],
        'weight': 0.15,
    },
]

# Selection parameters
TOP_N = 20
INDUSTRY_MAX_WEIGHT = 0.30

# IC validation parameters
IC_FORWARD_PERIOD = 20
IC_MIN_SAMPLES = 30
IC_MIN_DATES = 20
