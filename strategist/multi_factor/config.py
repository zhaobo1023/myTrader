# -*- coding: utf-8 -*-
"""
多因子选股配置

定义因子列表、方向、来源表、权重等配置。
"""

# 14 个基础因子定义
# (factor_name, source_table, source_column, direction)
# direction: -1 = low value better, +1 = high value better
FACTOR_DEFS = [
    # -- 估值因子 --
    {
        'name': 'pb',
        'table': 'trade_stock_valuation_factor',
        'column': 'pb',
        'direction': -1,
        'label': 'Low PB',
    },
    {
        'name': 'pe_ttm',
        'table': 'trade_stock_valuation_factor',
        'column': 'pe_ttm',
        'direction': -1,
        'label': 'Low PE',
    },
    {
        'name': 'market_cap',
        'table': 'trade_stock_valuation_factor',
        'column': 'market_cap',
        'direction': -1,
        'label': 'Small Cap',
    },
    # -- 基础因子 --
    {
        'name': 'volatility_20',
        'table': 'trade_stock_basic_factor',
        'column': 'volatility_20',
        'direction': -1,
        'label': 'Low Volatility',
    },
    {
        'name': 'close',
        'table': 'trade_stock_basic_factor',
        'column': 'close',
        'direction': -1,
        'label': 'Low Price',
    },
    {
        'name': 'mom_20',
        'table': 'trade_stock_basic_factor',
        'column': 'mom_20',
        'direction': 1,
        'label': 'Momentum 20D',
    },
    {
        'name': 'reversal_5',
        'table': 'trade_stock_basic_factor',
        'column': 'reversal_5',
        'direction': 1,
        'label': 'Reversal 5D',
    },
    # -- 扩展因子 --
    {
        'name': 'roe_ttm',
        'table': 'trade_stock_extended_factor',
        'column': 'roe_ttm',
        'direction': 1,
        'label': 'High ROE',
    },
    {
        'name': 'gross_margin',
        'table': 'trade_stock_extended_factor',
        'column': 'gross_margin',
        'direction': 1,
        'label': 'High Gross Margin',
    },
    {
        'name': 'net_profit_growth',
        'table': 'trade_stock_extended_factor',
        'column': 'net_profit_growth',
        'direction': 1,
        'label': 'Profit Growth',
    },
    {
        'name': 'revenue_growth',
        'table': 'trade_stock_extended_factor',
        'column': 'revenue_growth',
        'direction': 1,
        'label': 'Revenue Growth',
    },
    # -- 质量因子 --
    {
        'name': 'roa',
        'table': 'trade_stock_quality_factor',
        'column': 'roa',
        'direction': 1,
        'label': 'High ROA',
    },
    {
        'name': 'debt_ratio',
        'table': 'trade_stock_quality_factor',
        'column': 'debt_ratio',
        'direction': -1,
        'label': 'Low Leverage',
    },
    # -- 每日基本面 --
    {
        'name': 'dv_ttm',
        'table': 'trade_stock_daily_basic',
        'column': 'dv_ttm',
        'direction': 1,
        'label': 'High Dividend Yield',
    },
]

# 复合因子定义 (从基础因子计算)
COMPOSITE_FACTORS = [
    {
        'name': 'pb_roe',
        'formula': 'roe_ttm / pb',
        'requires': ['roe_ttm', 'pb'],
        'direction': 1,  # 越高越好: 高ROE + 低PB
        'label': 'PB-ROE',
        'filter': 'pb > 0',  # PB必须为正
    },
]

# 因子分组 (用于分组等权合成)
FACTOR_GROUPS = [
    {
        'name': 'value',
        'label': 'Value',
        'factors': ['pb', 'pe_ttm', 'close'],
        'weight': 0.25,
    },
    {
        'name': 'momentum',
        'label': 'Momentum/Reversal',
        'factors': ['mom_20', 'reversal_5'],
        'weight': 0.25,
    },
    {
        'name': 'quality',
        'label': 'Quality/Growth',
        'factors': ['roe_ttm', 'revenue_growth', 'net_profit_growth', 'roa'],
        'weight': 0.25,
    },
    {
        'name': 'risk',
        'label': 'Risk',
        'factors': ['volatility_20', 'market_cap'],
        'weight': 0.25,
    },
]

# 因子名列表 (基础 + 复合)
FACTORS = [f['name'] for f in FACTOR_DEFS] + [cf['name'] for cf in COMPOSITE_FACTORS]

# 因子方向映射
FACTOR_DIRECTIONS = {f['name']: f['direction'] for f in FACTOR_DEFS}
for cf in COMPOSITE_FACTORS:
    FACTOR_DIRECTIONS[cf['name']] = cf['direction']

# 因子标签
FACTOR_LABELS = {f['name']: f['label'] for f in FACTOR_DEFS}
for cf in COMPOSITE_FACTORS:
    FACTOR_LABELS[cf['name']] = cf['label']

# 默认选股参数
DEFAULT_TOP_N = 50
DEFAULT_REBALANCE_FREQ = 20  # 交易日

# IC 验证参数
IC_FORWARD_PERIOD = 20  # 前瞻收益率周期(天)
IC_MIN_SAMPLES = 30     # 截面最少股票数
IC_MIN_DATES = 20       # IC时间序列最少天数

# 过滤参数
FILTER_MIN_PRICE = 1.0        # 最低价格过滤
FILTER_EXCLUDE_ST = True       # 排除 ST / *ST
FILTER_MIN_LIST_DAYS = 250     # 上市至少250个交易日(约1年)
FILTER_EXCLUDE_KCBJ = True     # 排除科创板(688)和北交所(8/4)

# 行业权重上限 (Plan B: 行业分散)
INDUSTRY_MAX_WEIGHT = 0.20     # 单一行业最多占 Top N 的 20%
INDUSTRY_CAP_ENABLED = True    # 是否启用行业权重上限
