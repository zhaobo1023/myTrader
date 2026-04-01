# -*- coding: utf-8 -*-
"""load ETF daily close prices from trade_etf_daily"""

import logging
import sys
import os

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.db import execute_query

logger = logging.getLogger(__name__)


class DataLoader:
    """load close prices from trade_etf_daily"""

    def __init__(self, env: str = 'online'):
        self.env = env

    def load(self, ts_code: str, lookback_days: int = 400) -> pd.DataFrame:
        """
        load close prices for a single ETF

        Args:
            ts_code: e.g. '510300.SH'
            lookback_days: number of calendar days to look back

        Returns:
            DataFrame with columns: [trade_date, close], sorted by trade_date ASC
        """
        from datetime import timedelta
        end = pd.Timestamp.now().strftime('%Y-%m-%d')
        start = (pd.Timestamp.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        sql = """
            SELECT trade_date, close_price as close
            FROM trade_etf_daily
            WHERE fund_code = %s AND trade_date >= %s AND trade_date <= %s
            ORDER BY trade_date ASC
        """
        rows = execute_query(sql, (ts_code, start, end), env=self.env)
        if not rows:
            logger.warning(f"No data for {ts_code} in [{start}, {end}]")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])
        df = df.reset_index(drop=True)
        logger.info(f"Loaded {len(df)} rows for {ts_code}")
        return df

    def load_multi(self, ts_codes: list, lookback_days: int = 400) -> dict:
        """
        load close prices for multiple ETFs

        Returns:
            dict: {ts_code: DataFrame}
        """
        result = {}
        for code in ts_codes:
            df = self.load(code, lookback_days)
            if len(df) > 0:
                result[code] = df
        return result

    def get_latest_trade_date(self) -> str:
        """get the latest trade date in the database"""
        sql = "SELECT MAX(trade_date) as latest FROM trade_etf_daily"
        rows = execute_query(sql, env=self.env)
        if rows and rows[0]['latest']:
            return str(rows[0]['latest'])
        return ''
