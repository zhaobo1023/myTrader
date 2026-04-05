# -*- coding: utf-8 -*-
"""
Report Engine - Intelligent A-share research report generation.

Entry point: FiveStepAnalyzer
  .generate_fundamental(stock_code, stock_name) -> Dict[str, str]
  .generate_tech_section(stock_code, stock_name) -> str

Report types:
  fundamental   - five-step fundamental analysis (info gap/logic gap/expectation gap/catalysts/conclusion)
  technical     - technical analysis (MA/MACD/RSI/KDJ/BOLL/divergence)
  comprehensive - combined report (fundamental + technical)
"""
