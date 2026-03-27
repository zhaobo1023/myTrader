# -*- coding: utf-8 -*-
"""
Paper Trading 实盘验证系统

消除回测的 look-ahead bias，用真实时序验证 XGBoost 截面预测策略的有效性。

核心流程:
    信号日(周五) -> 生成信号 -> T+1 买入(收盘价) -> T+N 卖出(收盘价) -> 结算
"""

__version__ = '1.0.0'

from .config import PaperTradingConfig
from .position_manager import PositionManager
from .signal_generator import SignalGenerator
from .settlement import SettlementEngine
from .evaluator import PerformanceEvaluator
from .scheduler import PaperTradingScheduler

__all__ = [
    'PaperTradingConfig',
    'PositionManager',
    'SignalGenerator',
    'SettlementEngine',
    'PerformanceEvaluator',
    'PaperTradingScheduler',
]
