# -*- coding: utf-8 -*-
"""策略组合权重调度配置"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class AllocatorConfig:
    """权重调度配置"""
    
    # Base strategy weights (must sum to 1.0)
    base_weights: Dict[str, float] = field(default_factory=lambda: {
        'xgboost': 0.40,
        'doctor_tao': 0.35,
        'multi_factor': 0.25,
    })
    
    # Regime adjustments (delta to base)
    regime_adjustments: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        'BULL': {'xgboost': +0.05, 'doctor_tao': +0.10, 'multi_factor': -0.15},
        'BEAR': {'xgboost': -0.05, 'doctor_tao': -0.15, 'multi_factor': +0.20},
        'NEUTRAL': {'xgboost': 0, 'doctor_tao': 0, 'multi_factor': 0},
    })
    
    # Crowding penalty on momentum strategies
    crowding_penalties: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        'HIGH': {'doctor_tao': -0.10, 'xgboost': -0.05},
        'CRITICAL': {'doctor_tao': -0.20, 'xgboost': -0.10},
    })
    
    # Weight constraints
    min_weight: float = 0.05
    max_weight: float = 0.60
    
    # Output
    output_dir: str = 'output/portfolio_allocator'
