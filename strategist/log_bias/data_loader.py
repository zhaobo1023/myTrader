# -*- coding: utf-8 -*-
"""load ETF / CSI index daily close prices"""

import logging
import sys
import os
import time

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.db import execute_query

logger = logging.getLogger(__name__)

# Ensure proxy bypass for AKShare calls
_AKSHARE_NO_PROXY = 'push2.eastmoney.com,www.csindex.com.cn'


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


def _ensure_no_proxy():
    """Ensure NO_PROXY includes AKShare domains so proxy doesn't block requests."""
    _env = os.environ
    current = _env.get('NO_PROXY') or _env.get('no_proxy') or ''
    entries = set(e.strip() for e in current.split(',') if e.strip())
    for domain in _AKSHARE_NO_PROXY.split(','):
        entries.add(domain)
    result = ','.join(sorted(entries))
    _env['NO_PROXY'] = result
    _env['no_proxy'] = result


class IndexDataLoader:
    """Load close prices for CSI thematic indices via AKShare.

    Primary:  ak.stock_zh_index_hist_csindex  (CSI official website)
    Fallback: ak.stock_zh_index_daily_em      (eastmoney app, 399xxx only)
    """

    def __init__(self, delay: float = 0.3):
        self.delay = delay

    def load(self, code: str, lookback_days: int = 400) -> pd.DataFrame:
        """
        Load close prices for a single CSI index.

        Args:
            code: CSI index code, e.g. '930713'
            lookback_days: calendar days to look back

        Returns:
            DataFrame[trade_date, close] sorted ASC, or empty DataFrame
        """
        _ensure_no_proxy()
        import akshare as ak
        from datetime import timedelta

        end_str = pd.Timestamp.now().strftime('%Y%m%d')
        start_dt = pd.Timestamp.now() - timedelta(days=lookback_days)
        start_str = start_dt.strftime('%Y%m%d')

        # Method 1: CSI official website
        try:
            df = ak.stock_zh_index_hist_csindex(
                symbol=code, start_date=start_str, end_date=end_str,
            )
            if df is not None and not df.empty:
                out = pd.DataFrame({
                    'trade_date': pd.to_datetime(df['日期']),
                    'close': pd.to_numeric(df['收盘'], errors='coerce'),
                })
                out = out.dropna(subset=['close']).sort_values('trade_date').reset_index(drop=True)
                logger.info(f"[csindex] Loaded {len(out)} rows for {code}")
                return out
        except Exception as e:
            logger.debug(f"[csindex] {code} failed: {e}")

        # Method 2: eastmoney app (works for 399xxx codes)
        for prefix in ['sz', 'sh']:
            try:
                sym = f'{prefix}{code}'
                df = ak.stock_zh_index_daily_em(symbol=sym)
                if df is not None and not df.empty:
                    df['date'] = pd.to_datetime(df['date'])
                    out = df[df['date'] >= start_dt][['date', 'close']].copy()
                    out = out.rename(columns={'date': 'trade_date'})
                    out['close'] = pd.to_numeric(out['close'], errors='coerce')
                    out = out.dropna(subset=['close']).sort_values('trade_date').reset_index(drop=True)
                    if not out.empty:
                        logger.info(f"[em] Loaded {len(out)} rows for {sym}")
                        return out
            except Exception:
                continue

        logger.warning(f"No data for index {code} from any source")
        return pd.DataFrame()

    def load_multi(self, codes: list, lookback_days: int = 400) -> dict:
        """Load close prices for multiple CSI indices.

        Returns:
            dict: {code: DataFrame}
        """
        result = {}
        for code in codes:
            df = self.load(code, lookback_days)
            if not df.empty:
                result[code] = df
            time.sleep(self.delay)
        return result
