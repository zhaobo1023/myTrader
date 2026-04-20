# -*- coding: utf-8 -*-
"""Multi-dimensional crowding score aggregator"""
import logging
import numpy as np
import pandas as pd
from typing import List
from .config import CrowdingConfig
from .schemas import CrowdingScore

logger = logging.getLogger(__name__)


class CrowdingScorer:
    """Aggregate multiple signals into a composite crowding score (0-100)"""
    
    def __init__(self, config: CrowdingConfig = None):
        self.config = config or CrowdingConfig()
    
    def compute_northbound_deviation(self, north_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute northbound flow deviation in sigma units.
        deviation = (MA20 - MA60) / rolling_std_60
        """
        if north_df.empty:
            return pd.DataFrame()
        
        df = north_df.copy()
        short = self.config.north_short_window
        long = self.config.north_long_window
        
        df['ma_short'] = df['value'].rolling(window=short, min_periods=short).mean()
        df['ma_long'] = df['value'].rolling(window=long, min_periods=long).mean()
        df['std_long'] = df['value'].rolling(window=long, min_periods=long).std()
        
        # Deviation in sigma
        df['deviation'] = np.where(
            df['std_long'] > 0,
            (df['ma_short'] - df['ma_long']) / df['std_long'],
            0.0
        )
        return df[['deviation']]
    
    def score_component(self, value: float, component: str) -> float:
        """Convert a raw component value to a 0-100 score"""
        if component == 'turnover_hhi':
            # HHI percentile directly maps to 0-100
            return min(100, max(0, value * 100))
        
        elif component == 'northbound_deviation':
            # Absolute deviation: 0 sigma = 0, 3 sigma = 100
            return min(100, max(0, abs(value) / 3.0 * 100))
        
        elif component == 'margin_concentration':
            # Placeholder: 0-1 maps to 0-100
            return min(100, max(0, value * 100))
        
        elif component == 'svd_factor_concentration':
            # top1_var_ratio: 0.2=0, 0.5+=100
            normalized = (value - 0.20) / 0.30  # 0.2->0, 0.5->1
            return min(100, max(0, normalized * 100))
        
        return 0.0
    
    def compute_scores(self, hhi_df: pd.DataFrame, north_df: pd.DataFrame,
                       svd_df: pd.DataFrame, start_date: str = None) -> List[CrowdingScore]:
        """
        Compute composite crowding scores by merging all dimensions.
        """
        # Compute northbound deviation
        north_dev = self.compute_northbound_deviation(north_df) if not north_df.empty else pd.DataFrame()
        
        # Merge all on date
        result_dates = hhi_df.index if not hhi_df.empty else pd.DatetimeIndex([])
        
        if result_dates.empty:
            logger.warning("No dates available for crowding score calculation")
            return []
        
        scores = []
        weights = self.config.weights.copy()
        
        # If margin data unavailable, redistribute weight
        has_margin = False  # Currently no margin data source
        if not has_margin:
            margin_w = weights.pop('margin_concentration', 0)
            remaining = sum(weights.values())
            if remaining > 0:
                for k in weights:
                    weights[k] = weights[k] / remaining
        
        for dt in result_dates:
            if start_date and dt < pd.Timestamp(start_date):
                continue
            
            # Get component values
            hhi_pct = hhi_df.loc[dt, 'hhi_percentile'] if dt in hhi_df.index and pd.notna(hhi_df.loc[dt].get('hhi_percentile')) else None
            
            north_dev_val = None
            if not north_dev.empty and dt in north_dev.index:
                val = north_dev.loc[dt, 'deviation']
                if pd.notna(val):
                    north_dev_val = float(val)
            
            svd_val = None
            if not svd_df.empty and dt in svd_df.index:
                val = svd_df.loc[dt, 'top1_var_ratio']
                if pd.notna(val):
                    svd_val = float(val)
            
            # Score each component
            weighted_sum = 0.0
            total_weight = 0.0
            
            if hhi_pct is not None:
                s = self.score_component(float(hhi_pct), 'turnover_hhi')
                weighted_sum += s * weights.get('turnover_hhi', 0)
                total_weight += weights.get('turnover_hhi', 0)
            
            if north_dev_val is not None:
                s = self.score_component(north_dev_val, 'northbound_deviation')
                weighted_sum += s * weights.get('northbound_deviation', 0)
                total_weight += weights.get('northbound_deviation', 0)
            
            if svd_val is not None:
                s = self.score_component(svd_val, 'svd_factor_concentration')
                weighted_sum += s * weights.get('svd_factor_concentration', 0)
                total_weight += weights.get('svd_factor_concentration', 0)
            
            # Final score (normalize by available weights)
            if total_weight > 0:
                final_score = weighted_sum / total_weight
            else:
                continue
            
            # Determine level
            level = 'LOW'
            for lvl_name in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
                if final_score >= self.config.level_thresholds.get(lvl_name, 100):
                    level = lvl_name
                    break
            
            calc_date = dt.date() if hasattr(dt, 'date') else dt
            score = CrowdingScore(
                calc_date=calc_date,
                dimension='overall',
                dimension_id='',
                turnover_hhi=float(hhi_df.loc[dt, 'hhi_rolling']) if dt in hhi_df.index and pd.notna(hhi_df.loc[dt].get('hhi_rolling')) else None,
                turnover_hhi_percentile=float(hhi_pct) if hhi_pct is not None else None,
                northbound_deviation=north_dev_val,
                margin_concentration=None,
                svd_top1_ratio=svd_val,
                crowding_score=round(final_score, 2),
                crowding_level=level,
            )
            scores.append(score)
        
        logger.info(f"Computed {len(scores)} crowding scores")
        if scores:
            latest = scores[-1]
            logger.info(f"Latest: score={latest.crowding_score}, level={latest.crowding_level}")
        
        return scores
