# -*- coding: utf-8 -*-
"""
Hard-tech factor definitions and strategy parameters

IC-validated factor weights (Phase 1 results):
  - gross_margin IC=0.16 (strong), mom_20 IC=0.35 (strong)
  - rd_intensity IC=-0.06 (negative, use as filter not ranker)
  - rd_growth, gross_margin_trend weak

Strategy: rd_intensity > 3% as entry filter, then rank by factors.
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

# Factor direction mapping (for IC analysis -- all factors)
FACTOR_DIRECTIONS = {f['name']: f['direction'] for f in ALL_FACTOR_DEFS}

# Factor labels
FACTOR_LABELS = {f['name']: f['label'] for f in ALL_FACTOR_DEFS}

# Factor name list (for IC analysis)
HARDTECH_FACTORS = [f['name'] for f in ALL_FACTOR_DEFS]

# Factor group structure (IC-validated, used by preset strategy system + backtest)
# rd_intensity excluded from ranking (negative IC=-0.06), used as entry filter instead.
FACTOR_GROUPS = [
    {
        'name': 'quality',
        'label': 'Quality',
        'factors': ['gross_margin', 'net_profit_growth'],
        'weight': 0.25,
    },
    {
        'name': 'momentum',
        'label': 'Momentum',
        'factors': ['rps_250', 'mom_20'],
        'weight': 0.30,
    },
    {
        'name': 'innovation',
        'label': 'Innovation',
        'factors': ['rd_growth', 'gross_margin_trend'],
        'weight': 0.20,
    },
    {
        'name': 'growth',
        'label': 'Growth',
        'factors': ['revenue_growth'],
        'weight': 0.10,
    },
    {
        'name': 'valuation',
        'label': 'Valuation',
        'factors': ['pe_ttm'],
        'weight': 0.15,
    },
]

# Selection parameters (for preset strategy system)
TOP_N = 20
INDUSTRY_MAX_WEIGHT = 0.25

# ========================================================================
# Strategy parameters (IC-validated weights for stock selection)
# ========================================================================

# R&D intensity threshold for hard-tech stock screening
RD_INTENSITY_THRESHOLD = 0.03

# Hard-tech industries for stock pool
HARD_TECH_INDUSTRIES = [
    '电子', '计算机', '通信', '电力设备',
    '机械设备', '国防军工', '医药生物', '汽车',
    '有色金属', '化工',
]

# Strategy ranking factors (IC-validated, rd_intensity excluded from ranking)
# Same as FACTOR_GROUPS above, kept as alias for backtest/sim_pool compatibility.
STRATEGY_FACTOR_GROUPS = FACTOR_GROUPS

# Factor directions for strategy
STRATEGY_FACTOR_DIRECTIONS = FACTOR_DIRECTIONS

# Backtest parameters
BACKTEST_PARAMS = {
    'top_n': 20,
    'rebalance_freq': 20,      # 20 trading days = monthly
    'buy_cost_rate': 0.0003,   # 0.03% commission
    'sell_cost_rate': 0.0013,  # 0.03% commission + 0.1% stamp tax
    'slippage_rate': 0.001,    # 0.1% per side
    'industry_max_weight': 0.20,
    'benchmark_code': '000300.SH',
}

# IC validation parameters
IC_FORWARD_PERIOD = 20
IC_MIN_SAMPLES = 30
IC_MIN_DATES = 20
