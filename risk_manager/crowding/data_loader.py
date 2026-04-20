# -*- coding: utf-8 -*-
"""拥挤度数据加载"""
import logging
import pandas as pd
from config.db import execute_query

logger = logging.getLogger(__name__)


class CrowdingDataLoader:
    def __init__(self, env: str = 'online'):
        self.env = env
    
    def load_daily_turnover(self, start_date: str, end_date: str = None) -> pd.DataFrame:
        """
        Load daily turnover by stock with industry info.
        Returns DataFrame with columns: trade_date, stock_code, turnover_amount, sw_level1
        """
        sql = """
            SELECT d.trade_date, d.stock_code, d.turnover_amount, b.sw_level1
            FROM trade_stock_daily d
            LEFT JOIN trade_stock_basic b ON d.stock_code = b.stock_code
            WHERE d.trade_date >= %s
              AND d.turnover_amount > 0
        """
        params = [start_date]
        if end_date:
            sql += " AND d.trade_date <= %s"
            params.append(end_date)
        sql += " ORDER BY d.trade_date"
        
        rows = execute_query(sql, tuple(params), env=self.env)
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['turnover_amount'] = df['turnover_amount'].astype(float)
        return df
    
    def load_northbound_flow(self, start_date: str, end_date: str = None) -> pd.DataFrame:
        """
        Load northbound flow from macro_data table.
        Returns DataFrame with date index and 'value' column.
        """
        sql = "SELECT date, value FROM macro_data WHERE indicator = 'north_flow' AND date >= %s"
        params = [start_date]
        if end_date:
            sql += " AND date <= %s"
            params.append(end_date)
        sql += " ORDER BY date ASC"
        
        rows = execute_query(sql, tuple(params), env=self.env)
        if not rows:
            logger.warning("No northbound flow data found")
            return pd.DataFrame(columns=['value'])
        
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = df['value'].astype(float)
        df = df.set_index('date').sort_index()
        return df
    
    def load_svd_state(self, start_date: str, end_date: str = None) -> pd.DataFrame:
        """
        Load SVD market state for top1 variance ratio.
        Uses window_size=20 for short-term signal.
        """
        sql = """
            SELECT calc_date, top1_var_ratio, top3_var_ratio
            FROM trade_svd_market_state
            WHERE window_size = 20 AND universe_type = '全A'
              AND calc_date >= %s
        """
        params = [start_date]
        if end_date:
            sql += " AND calc_date <= %s"
            params.append(end_date)
        sql += " ORDER BY calc_date ASC"
        
        rows = execute_query(sql, tuple(params), env=self.env)
        if not rows:
            logger.warning("No SVD state data found")
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        df['calc_date'] = pd.to_datetime(df['calc_date'])
        df['top1_var_ratio'] = df['top1_var_ratio'].astype(float)
        df = df.set_index('calc_date').sort_index()
        return df
