# -*- coding: utf-8 -*-
"""拥挤度监控配置"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class CrowdingConfig:
    """拥挤度监控参数"""
    
    # HHI rolling window
    hhi_rolling_window: int = 20
    
    # Percentile lookback
    percentile_lookback: int = 250
    
    # Northbound flow deviation windows
    north_short_window: int = 20
    north_long_window: int = 60
    
    # SVD concentration threshold
    svd_critical_threshold: float = 0.50  # top1 > 50% = extreme crowding
    
    # Scoring weights
    weights: Dict[str, float] = field(default_factory=lambda: {
        'turnover_hhi': 0.35,
        'northbound_deviation': 0.25,
        'margin_concentration': 0.15,
        'svd_factor_concentration': 0.25,
    })
    
    # Level thresholds (score 0-100)
    level_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'LOW': 25,
        'MEDIUM': 50,
        'HIGH': 75,
        'CRITICAL': 90,
    })
    
    # Output
    output_dir: str = 'output/crowding_monitor'
