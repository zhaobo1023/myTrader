# -*- coding: utf-8 -*-
"""
Market Dashboard configuration - thresholds and signal level definitions.
No emoji - plain text labels only.
"""

# ============================================================
# Section 1: Market Temperature
# ============================================================

# Volume / MA20 ratio thresholds -> 5 levels
VOLUME_RATIO_THRESHOLDS = [0.7, 0.85, 1.15, 1.5]
VOLUME_RATIO_LEVELS = ['freezing', 'cold', 'normal', 'active', 'overheated']

# Turnover rate percentile rank thresholds -> 5 levels
TURNOVER_PCT_THRESHOLDS = [15, 30, 70, 85]
TURNOVER_PCT_LEVELS = ['freezing', 'cold', 'normal', 'active', 'overheated']

# Advance/decline ratio thresholds
ADV_DEC_RATIO_THRESHOLDS = [0.5, 0.8, 1.2, 2.0]
ADV_DEC_LEVELS = ['extreme_weak', 'weak', 'balanced', 'strong', 'extreme_strong']

# Margin balance 5d change rate (%)
MARGIN_CHANGE_THRESHOLDS = [-1.0, -0.3, 0.3, 1.0]
MARGIN_CHANGE_LEVELS = ['contracting_fast', 'contracting', 'stable', 'expanding', 'expanding_fast']

# Temperature composite score (0-100) -> 5 levels
TEMPERATURE_THRESHOLDS = [20, 35, 65, 80]
TEMPERATURE_LEVELS = ['freezing', 'cold', 'normal', 'active', 'overheated']
TEMPERATURE_LABELS = {
    'freezing': '冰点',
    'cold': '低迷',
    'normal': '常温',
    'active': '活跃',
    'overheated': '过热',
}

# ============================================================
# Section 2: Trend & Direction
# ============================================================

# ADX thresholds
ADX_THRESHOLDS = [20, 25]
ADX_LEVELS = ['consolidating', 'weak_trend', 'trending']

# Trend composite -> 5 levels (direction * confidence)
TREND_LEVELS = ['panic_drop', 'weak_down', 'consolidating', 'mild_up', 'strong_up']
TREND_LABELS = {
    'strong_up': '强势上攻',
    'mild_up': '温和上行',
    'consolidating': '震荡蓄势',
    'weak_down': '弱势调整',
    'panic_drop': '恐慌下跌',
}

# ============================================================
# Section 3: Sentiment / Fear-Greed
# ============================================================

# A-share local fear-greed index (0-100) -> 5 levels
FEAR_GREED_THRESHOLDS = [20, 40, 60, 80]
FEAR_GREED_LEVELS = ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed']
FEAR_GREED_LABELS = {
    'extreme_fear': '极度恐惧',
    'fear': '恐惧',
    'neutral': '中性',
    'greed': '贪婪',
    'extreme_greed': '极度贪婪',
}

# QVIX thresholds
QVIX_THRESHOLDS = [15, 25, 35]
QVIX_LEVELS = ['complacent', 'normal', 'anxious', 'panic']

# ============================================================
# Section 4: Style Rotation
# (Uses existing tri-prism signals from market_overview)
# ============================================================

STYLE_LABELS = {
    'large_cap': '大盘主导',
    'small_cap': '小盘主导',
    'growth': '成长主导',
    'value': '价值主导',
    'neutral': '均衡',
}

STRENGTH_LABELS = {
    'confirmed': '确认',
    'weak': '偏向',
    'neutral': '',
}

# ============================================================
# Section 5: Stock-Bond Dynamics
# (Uses existing calc_stock_bond_spread)
# ============================================================

STOCK_BOND_LEVELS = ['bond_preferred', 'neutral', 'stock_attractive']
STOCK_BOND_LABELS = {
    'bond_preferred': '债券更优',
    'neutral': '中性',
    'stock_attractive': '股票吸引力强',
}

# ============================================================
# Section 6: Macro Backdrop
# ============================================================

MACRO_LEVELS = ['headwind', 'neutral', 'tailwind']
MACRO_LABELS = {
    'headwind': '逆风',
    'neutral': '中性',
    'tailwind': '顺风',
}

# ============================================================
# Tracked indices for trend section
# ============================================================

INDEX_CONFIG = [
    {'key': 'idx_sh', 'name': '上证', 'code': 'sh000001'},
    {'key': 'idx_csi300', 'name': '沪深300', 'code': 'sh000300'},
    {'key': 'idx_gem', 'name': '创业板', 'code': 'sz399006'},
    {'key': 'idx_csi1000', 'name': '中证1000', 'code': 'sh000852'},
]
