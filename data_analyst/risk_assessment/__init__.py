# -*- coding: utf-8 -*-
"""
分层风控评估模块

5 层风控体系:
  L1 宏观/系统性风险 -> 整体仓位水位
  L2 市场状态/相关性 -> 组合分散度
  L3 行业风险暴露    -> 行业集中度
  L4 个股基本面      -> 个股持仓建议
  L5 交易执行        -> 下单拦截
"""
from .scanner import scan_portfolio_v2
from .report import generate_report_v2

__all__ = ['scan_portfolio_v2', 'generate_report_v2']
