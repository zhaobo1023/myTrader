# -*- coding: utf-8 -*-
"""牛熊三指标监控配置"""
from dataclasses import dataclass, field


@dataclass
class BullBearConfig:
    # MA windows
    ma_short: int = 20
    ma_long: int = 60

    # 10Y bond thresholds
    bond_bull_threshold: float = 2.5  # below this = bullish for stocks
    bond_bear_threshold: float = 3.0  # above this = bearish for stocks

    # USDCNY thresholds
    usdcny_rise_pct: float = 0.01  # 20d rise > 1% = bearish

    # Regime thresholds
    bull_threshold: int = 2   # composite >= 2 => BULL
    bear_threshold: int = -2  # composite <= -2 => BEAR

    # Data sources (indicator names in macro_data table)
    bond_indicator: str = 'cn_10y_bond'
    usdcny_indicator: str = 'usdcny'
    dividend_indicator: str = 'idx_dividend'
    csi300_indicator: str = 'idx_csi300'

    # Output
    output_dir: str = 'output/bull_bear_monitor'
