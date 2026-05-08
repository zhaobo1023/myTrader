# -*- coding: utf-8 -*-
"""
Hard-tech multi-factor strategy module
"""
from .config import (
    HARDTECH_FACTORS, FACTOR_DIRECTIONS, FACTOR_GROUPS,
    STRATEGY_FACTOR_GROUPS, STRATEGY_FACTOR_DIRECTIONS,
    BACKTEST_PARAMS, RD_INTENSITY_THRESHOLD,
)
from .screener import screen_hardtech_stocks
