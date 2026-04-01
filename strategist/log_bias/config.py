# -*- coding: utf-8 -*-
"""log_bias config"""

from dataclasses import dataclass
from dataclasses import field
from typing import Dict

DEFAULT_ETFS: Dict[str, str] = {
    # tech growth
    '159995.SZ': 'chipETF',
    '515050.SH': '5GETF',
    '516160.SH': 'newEnergyCarETF',
    '515790.SH': 'solarETF',
    '159941.SZ': 'nasdaqETF',
    # consumer & pharma
    '512690.SH': 'liquorETF',
    '512010.SH': 'pharmaETF',
    # cyclical & finance
    '512880.SH': 'securitiesETF',
    '515220.SH': 'coalETF',
    '518880.SH': 'goldETF',
    # broad base
    '510300.SH': 'hs300ETF',
    '588000.SH': 'star50ETF',
}

OVERHEAT_THRESHOLD = 15.0
BREAKOUT_THRESHOLD = 5.0
STALL_THRESHOLD = -5.0
COOLDOWN_DAYS = 10
EMA_WINDOW = 20


@dataclass
class LogBiasConfig:
    """config for log bias module"""
    etfs: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ETFS))
    ema_window: int = EMA_WINDOW
    overheat_threshold: float = OVERHEAT_THRESHOLD
    breakout_threshold: float = BREAKOUT_THRESHOLD
    stall_threshold: float = STALL_THRESHOLD
    cooldown_days: int = COOLDOWN_DAYS
    lookback_days: int = 400
    output_dir: str = '/Users/zhaobo/Documents/notes/Finance/Output'
    log_dir: str = 'output/log_bias'
    db_env: str = 'online'
