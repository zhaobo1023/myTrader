# -*- coding: utf-8 -*-
"""
多因子选股配置

定义因子列表、方向、来源表、权重等配置。
"""

# 6 个核心因子定义
# (factor_name, source_table, source_column, direction)
# direction: -1 = low value better, +1 = high value better
FACTOR_DEFS = [
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
        'direction': 1,
        'label': 'Large Cap',
    },
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
        'name': 'roe_ttm',
        'table': 'trade_stock_extended_factor',
        'column': 'roe_ttm',
        'direction': 1,
        'label': 'High ROE',
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

# 过滤: 剔除 ST / 停牌 / 上市不足60天
FILTER_MIN_PRICE = 1.0  # 最低价格过滤
