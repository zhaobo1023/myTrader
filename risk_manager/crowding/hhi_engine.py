# -*- coding: utf-8 -*-
"""HHI (Herfindahl-Hirschman Index) calculation engine"""
import logging
import numpy as np
import pandas as pd
from .config import CrowdingConfig

logger = logging.getLogger(__name__)


class HHIEngine:
    """Calculate industry turnover concentration using HHI"""
    
    def __init__(self, config: CrowdingConfig = None):
        self.config = config or CrowdingConfig()
    
    def compute_daily_hhi(self, turnover_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute daily HHI of industry turnover shares.
        
        HHI = sum(share_i^2) where share_i = industry_i_turnover / total_turnover
        
        Args:
            turnover_df: DataFrame with columns [trade_date, stock_code, turnover_amount, sw_level1]
        
        Returns:
            DataFrame with date index and 'hhi' column
        """
        if turnover_df.empty:
            return pd.DataFrame(columns=['hhi'])
        
        # Group by date and industry
        daily_industry = turnover_df.groupby(['trade_date', 'sw_level1'])['turnover_amount'].sum().reset_index()
        daily_total = turnover_df.groupby('trade_date')['turnover_amount'].sum().reset_index()
        daily_total.columns = ['trade_date', 'total_amount']
        
        merged = daily_industry.merge(daily_total, on='trade_date')
        merged['share'] = merged['turnover_amount'] / merged['total_amount']
        merged['share_sq'] = merged['share'] ** 2
        
        # HHI per day
        hhi_daily = merged.groupby('trade_date')['share_sq'].sum().reset_index()
        hhi_daily.columns = ['trade_date', 'hhi']
        hhi_daily = hhi_daily.set_index('trade_date').sort_index()
        
        return hhi_daily
    
    def compute_rolling_hhi(self, hhi_daily: pd.DataFrame) -> pd.DataFrame:
        """
        Compute rolling mean HHI and its percentile rank.
        
        Returns DataFrame with columns: hhi, hhi_rolling, hhi_percentile
        """
        if hhi_daily.empty:
            return pd.DataFrame()
        
        df = hhi_daily.copy()
        window = self.config.hhi_rolling_window
        lookback = self.config.percentile_lookback
        
        # Rolling mean
        df['hhi_rolling'] = df['hhi'].rolling(window=window, min_periods=window).mean()
        
        # Rolling percentile (rank within lookback window)
        df['hhi_percentile'] = df['hhi_rolling'].rolling(
            window=lookback, min_periods=min(60, lookback)
        ).apply(lambda x: (x.values[-1] >= x.values[:-1]).mean() if len(x) > 1 else 0.5, raw=False)
        
        return df
