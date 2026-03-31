# -*- coding: utf-8 -*-
"""
持仓技术面扫描模块

每日盘后自动扫描持仓股票的技术面状态，生成 Markdown 报告。
"""
from .config import ScanConfig
from .run_scan import run_daily_scan

__all__ = ['ScanConfig', 'run_daily_scan']
