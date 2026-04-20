# -*- coding: utf-8 -*-
"""牛熊指标数据加载"""
import logging
import pandas as pd
from config.db import execute_query

logger = logging.getLogger(__name__)


class BullBearDataLoader:
    def __init__(self, env: str = 'online'):
        self.env = env

    def load_indicator(self, indicator: str, start_date: str, end_date: str = None) -> pd.DataFrame:
        """Load indicator data from macro_data table, returns DataFrame with date index and 'value' column"""
        sql = "SELECT date, value FROM macro_data WHERE indicator = %s AND date >= %s"
        params = [indicator, start_date]
        if end_date:
            sql += " AND date <= %s"
            params.append(end_date)
        sql += " ORDER BY date ASC"

        rows = execute_query(sql, tuple(params), env=self.env)
        if not rows:
            logger.warning(f"No data for indicator={indicator} from {start_date}")
            return pd.DataFrame(columns=['date', 'value'])

        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = df['value'].astype(float)
        df = df.set_index('date').sort_index()
        return df

    def load_all_indicators(self, start_date: str, end_date: str = None, config=None) -> dict:
        """Load all 4 indicators needed for bull/bear analysis"""
        from .config import BullBearConfig
        cfg = config or BullBearConfig()

        # Need extra lookback for MA calculation
        lookback_start = pd.Timestamp(start_date) - pd.Timedelta(days=120)
        lookback_str = lookback_start.strftime('%Y-%m-%d')

        data = {
            'bond': self.load_indicator(cfg.bond_indicator, lookback_str, end_date),
            'usdcny': self.load_indicator(cfg.usdcny_indicator, lookback_str, end_date),
            'dividend': self.load_indicator(cfg.dividend_indicator, lookback_str, end_date),
            'csi300': self.load_indicator(cfg.csi300_indicator, lookback_str, end_date),
        }
        return data
