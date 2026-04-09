# -*- coding: utf-8 -*-
"""
Microcap PEG 策略回测框架

核心逻辑：
1. 动态股票池：每日市值后 20% 的股票（排除 ST/*ST、PE_TTM <= 0）
2. 因子计算：PEG = PE_TTM / (EPS增速 * 100)
3. 回测引擎：按因子排名选股，T+1 买入，T+1+hold_days 卖出

使用方式：
  python -m strategist.microcap.run_backtest --start 2024-01-01 --end 2025-12-31
"""
