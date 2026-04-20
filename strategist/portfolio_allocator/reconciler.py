# -*- coding: utf-8 -*-
"""Target vs current weight reconciliation"""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class Reconciler:
    """Compare target weights to current allocation and generate rebalance suggestions"""
    
    def __init__(self, threshold_pct: float = 5.0):
        """
        Args:
            threshold_pct: Minimum weight change (%) to trigger rebalance suggestion
        """
        self.threshold_pct = threshold_pct
    
    def reconcile(self, target_weights: Dict[str, float], 
                  current_weights: Optional[Dict[str, float]] = None) -> List[Dict]:
        """
        Compare target vs current and generate suggestions.
        
        Returns list of dicts: [{'strategy': str, 'current': float, 'target': float, 'action': str}]
        """
        if current_weights is None:
            # No current data, just show targets
            return [
                {
                    'strategy': s,
                    'current': None,
                    'target': round(w * 100, 1),
                    'action': 'SET',
                    'delta': None,
                }
                for s, w in target_weights.items()
            ]
        
        suggestions = []
        for strategy, target_w in target_weights.items():
            current_w = current_weights.get(strategy, 0.0)
            delta = (target_w - current_w) * 100
            
            if abs(delta) < self.threshold_pct:
                action = 'HOLD'
            elif delta > 0:
                action = 'INCREASE'
            else:
                action = 'DECREASE'
            
            suggestions.append({
                'strategy': strategy,
                'current': round(current_w * 100, 1),
                'target': round(target_w * 100, 1),
                'action': action,
                'delta': round(delta, 1),
            })
        
        return suggestions
