# -*- coding: utf-8 -*-
"""Strategy weight calculation engine"""
import logging
from typing import List, Dict
from .config import AllocatorConfig
from .schemas import StrategyWeight
from datetime import date as date_type

logger = logging.getLogger(__name__)


class WeightEngine:
    """Compute target strategy weights based on regime and crowding"""
    
    def __init__(self, config: AllocatorConfig = None):
        self.config = config or AllocatorConfig()
    
    def compute_weights(self, calc_date: date_type, regime: str, crowding_level: str) -> List[StrategyWeight]:
        """
        Compute final weights for each strategy.
        
        Steps:
        1. Start with base weights
        2. Apply regime adjustment
        3. Apply crowding penalty
        4. Clamp to [min_weight, max_weight]
        5. Normalize to sum = 1.0
        """
        results = []
        raw_weights: Dict[str, float] = {}
        adjustments: Dict[str, Dict[str, float]] = {}
        
        for strategy, base_w in self.config.base_weights.items():
            # Regime adjustment
            regime_adj = self.config.regime_adjustments.get(regime, {}).get(strategy, 0.0)
            
            # Crowding penalty
            crowding_adj = 0.0
            if crowding_level in self.config.crowding_penalties:
                crowding_adj = self.config.crowding_penalties[crowding_level].get(strategy, 0.0)
            
            raw_w = base_w + regime_adj + crowding_adj
            raw_weights[strategy] = raw_w
            adjustments[strategy] = {'regime': regime_adj, 'crowding': crowding_adj}
        
        # Clamp
        clamped = {
            s: max(self.config.min_weight, min(self.config.max_weight, w))
            for s, w in raw_weights.items()
        }
        
        # Normalize to sum=1
        total = sum(clamped.values())
        if total > 0:
            normalized = {s: w / total for s, w in clamped.items()}
        else:
            n = len(clamped)
            normalized = {s: 1.0 / n for s in clamped}
        
        # Build results
        for strategy in self.config.base_weights:
            sw = StrategyWeight(
                calc_date=calc_date,
                strategy_name=strategy,
                base_weight=self.config.base_weights[strategy],
                regime_adjustment=adjustments[strategy]['regime'],
                crowding_adjustment=adjustments[strategy]['crowding'],
                final_weight=round(normalized[strategy], 4),
                regime=regime,
                crowding_level=crowding_level,
            )
            results.append(sw)
        
        return results
