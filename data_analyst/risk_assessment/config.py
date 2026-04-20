# -*- coding: utf-8 -*-

# L1 宏观风险分 -> 建议仓位上限
MACRO_POSITION_LIMITS = {
    (0, 30): 1.0,
    (30, 50): 0.8,
    (50, 70): 0.6,
    (70, 85): 0.4,
    (85, 100): 0.3,
}

# L1 权重
MACRO_WEIGHTS = {
    'fear_index': 0.30,
    'vix': 0.20,
    'northflow': 0.15,
    'yield_spread': 0.15,
    'commodity': 0.10,
    'fx': 0.10,
}

# L2 SVD 市场状态风险分
SVD_STATE_SCORES = {'齐涨齐跌': 85, '板块分化': 50, '个股行情': 20}

# L2 相关性风险分
CORR_RISK_SCORES = {(0.6, 1.1): 85, (0.4, 0.6): 55, (0.0, 0.4): 25}

# L3 行业集中度
SECTOR_CONCENTRATION_THRESHOLDS = [(0.5, 85), (0.3, 60), (0.0, 25)]

# L3 高估阈值 (pe_percentile_5y)
SECTOR_OVERVALUED_THRESHOLD = 0.70

# 风险分级
RISK_LEVELS = [(0, 30, 'LOW'), (30, 50, 'MEDIUM'), (50, 70, 'HIGH'), (70, 100, 'CRITICAL')]

# L4 个股止损线
STOP_LOSS_PCTS = {'L1': 0.15, 'L2': 0.08, 'L3': 0.08}

# 数据依赖最大延迟天数
DATA_MAX_DELAY_DAYS = {
    'trade_stock_daily': 1,
    'sw_industry_valuation': 1,
    'trade_svd_market_state': 1,
    'trade_fear_index': 2,
    'trade_technical_indicator': 1,
    'trade_stock_rps': 1,
    'trade_news_sentiment': 3,
}
