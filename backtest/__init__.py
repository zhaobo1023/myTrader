# -*- coding: utf-8 -*-
"""
通用回测框架

提供面向个股的回测引擎，支持：
- 多股票组合管理
- 完整的资金管理（现金+持仓）
- 手续费、滑点、印花税
- 止损、止盈、持仓到期
- 完整的回测指标计算
- 基准对比
"""

from .config import BacktestConfig
from .engine import BacktestEngine
from .portfolio import Portfolio, Position
from .metrics import BacktestResult, MetricsCalculator
from .report import ReportGenerator

__all__ = [
    'BacktestConfig',
    'BacktestEngine',
    'Portfolio',
    'Position',
    'BacktestResult',
    'MetricsCalculator',
    'ReportGenerator',
]
