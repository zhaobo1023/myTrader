# -*- coding: utf-8 -*-
"""
Risk Rule Engine

7-rule risk engine with scanner and daily report capabilities.
Migrated from trader project.

Usage:
    from risk_manager.rule_engine import RiskEngine, RiskConfig
    engine = RiskEngine(RiskConfig())
    decision = engine.check_stock('600519.SH', price=1800)
"""
from .base import BaseRule
from .config import RiskConfig
from .engine import RiskEngine
from .models import (
    AggregatedDecision,
    Decision,
    RiskContext,
    RiskDecision,
)
from .hooks import RiskHook, LoggingHook
from .audit import AuditLog
from .atr import calc_atr
from .sizing import calc_atr_position, ATRSizingResult
from .scanner import scan_portfolio, scan_watchlist
from .daily_report import generate_risk_report, push_risk_report

__all__ = [
    'RiskEngine',
    'RiskConfig',
    'BaseRule',
    'Decision',
    'RiskDecision',
    'RiskContext',
    'AggregatedDecision',
    'RiskHook',
    'LoggingHook',
    'AuditLog',
    'calc_atr',
    'calc_atr_position',
    'ATRSizingResult',
    'scan_portfolio',
    'scan_watchlist',
    'generate_risk_report',
    'push_risk_report',
]
