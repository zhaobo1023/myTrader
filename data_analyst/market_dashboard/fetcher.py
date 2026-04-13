# -*- coding: utf-8 -*-
"""
Market Dashboard Fetcher - collects new market-level indicators.

Writes to the `macro_data` table with appropriate indicator names.
Run daily after market close (16:30+).

Indicators fetched:
  - market_volume: Total A-share market volume (two exchanges)
  - advance_count / decline_count: Number of advancing/declining stocks
  - limit_up_count / limit_down_count: Limit up/down stock count
  - margin_balance / margin_net_buy: Margin trading data
  - new_high_60d / new_low_60d: 60-day new high/low count
  - seal_rate: Limit-up holding rate (seal rate)

No emoji - plain text labels only.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, date
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_update

logger = logging.getLogger(__name__)

UPSERT_SQL = """
    INSERT INTO macro_data (date, indicator, value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE value = VALUES(value)
"""


def _normalize_date(d: str) -> str:
    """Normalize date string to YYYY-MM-DD format."""
    d = d.strip().replace('/', '-')
    if len(d) == 8 and '-' not in d:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _to_compact(d: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD for AKShare APIs."""
    return _normalize_date(d).replace('-', '')


def _save(trade_date: str, indicator: str, value, env: str = 'online'):
    """Upsert a single indicator value into macro_data."""
    if value is None:
        return
    trade_date = _normalize_date(trade_date)
    try:
        execute_update(UPSERT_SQL, (trade_date, indicator, float(value)), env=env)
        logger.info("[OK] %s %s = %s", trade_date, indicator, value)
    except Exception as e:
        logger.error("[FAIL] %s %s: %s", trade_date, indicator, e)


def fetch_market_volume(trade_date: str = None, env: str = 'online'):
    """
    Fetch total A-share market volume from index data.
    Uses Shanghai Composite (sh000001) volume as proxy or AKShare.
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')

    try:
        # Use AKShare index data for Shanghai composite
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is not None and not df.empty:
            df['date'] = df['date'].astype(str)
            row = df[df['date'] == trade_date]
            if row.empty:
                # Try latest available date
                row = df.tail(1)
                trade_date = str(row.iloc[0]['date'])

            volume = float(row.iloc[0]['volume'])
            _save(trade_date, 'market_volume', volume, env=env)
            return volume
    except Exception as e:
        logger.error("fetch_market_volume failed: %s", e)
    return None


def fetch_advance_decline(trade_date: str = None, env: str = 'online'):
    """
    Fetch number of advancing and declining stocks.
    Uses AKShare real-time snapshot and counts by change_pct.
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')

    try:
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            logger.warning("stock_zh_a_spot_em returned empty")
            return

        # Column name may vary - try common names
        pct_col = None
        for col_name in ['涨跌幅', '涨跌百分比', 'change_pct']:
            if col_name in df.columns:
                pct_col = col_name
                break

        if pct_col is None:
            logger.warning("Cannot find change percent column in spot data. Columns: %s", list(df.columns))
            return

        changes = df[pct_col].astype(float)
        advance = int((changes > 0).sum())
        decline = int((changes < 0).sum())
        flat = int((changes == 0).sum())

        _save(trade_date, 'advance_count', advance, env=env)
        _save(trade_date, 'decline_count', decline, env=env)
        _save(trade_date, 'flat_count', flat, env=env)

        logger.info("Advance: %d, Decline: %d, Flat: %d", advance, decline, flat)
    except Exception as e:
        logger.error("fetch_advance_decline failed: %s", e)


def fetch_limit_up_down(trade_date: str = None, env: str = 'online'):
    """
    Fetch limit-up and limit-down stock count + seal rate.
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y%m%d')
    else:
        trade_date = _to_compact(trade_date)

    try:
        # Limit up pool
        df_up = ak.stock_zt_pool_em(date=trade_date)
        limit_up = len(df_up) if df_up is not None and not df_up.empty else 0

        # Limit down pool
        try:
            df_down = ak.stock_zt_pool_dtgc_em(date=trade_date)
            limit_down = len(df_down) if df_down is not None and not df_down.empty else 0
        except Exception:
            limit_down = 0

        date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        _save(date_str, 'limit_up_count', limit_up, env=env)
        _save(date_str, 'limit_down_count', limit_down, env=env)

        # Seal rate: count stocks that stayed at limit up until close
        if df_up is not None and not df_up.empty and limit_up > 0:
            # stock_zt_pool_em returns stocks at limit-up at close
            # For seal rate, we also need "曾涨停" (stocks that touched limit up)
            try:
                df_touched = ak.stock_zt_pool_previous_em(date=trade_date)
                total_touched = limit_up + (len(df_touched) if df_touched is not None else 0)
                seal_rate = limit_up / total_touched * 100 if total_touched > 0 else 0
            except Exception:
                seal_rate = 100.0 if limit_up > 0 else 0
            _save(date_str, 'seal_rate', round(seal_rate, 1), env=env)

        logger.info("Limit up: %d, Limit down: %d", limit_up, limit_down)
    except Exception as e:
        logger.error("fetch_limit_up_down failed: %s", e)


def fetch_margin_data(trade_date: str = None, env: str = 'online'):
    """
    Fetch margin balance and net buy data.
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y%m%d')
    else:
        trade_date = _to_compact(trade_date)

    try:
        # Shanghai margin data
        df_sh = ak.stock_margin_sse(
            start_date=(datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=10)).strftime('%Y%m%d'),
            end_date=trade_date,
        )
        if df_sh is not None and not df_sh.empty:
            latest = df_sh.iloc[-1]

            # Determine date from data
            date_col = None
            for c in df_sh.columns:
                if '日期' in str(c):
                    date_col = c
                    break
            if date_col and latest[date_col] is not None:
                date_str = _normalize_date(str(latest[date_col]))
            else:
                date_str = _normalize_date(trade_date)

            # Margin balance and net buy - find columns by keyword matching
            balance_col = None
            buy_col = None
            for col in df_sh.columns:
                col_str = str(col)
                if '余额' in col_str and '融资' in col_str:
                    balance_col = col
                if '买入' in col_str and '融资' in col_str:
                    buy_col = col

            if balance_col:
                balance = float(latest[balance_col])
                _save(date_str, 'margin_balance', balance, env=env)
            else:
                logger.warning("Cannot find margin balance column. Columns: %s", list(df_sh.columns))

            if buy_col:
                buy = float(latest[buy_col])
                _save(date_str, 'margin_net_buy', buy, env=env)
            else:
                logger.warning("Cannot find margin buy column. Columns: %s", list(df_sh.columns))

    except Exception as e:
        logger.error("fetch_margin_data failed: %s", e)


def fetch_new_high_low(trade_date: str = None, env: str = 'online'):
    """
    Calculate 60-day new high/low count from trade_stock_daily.
    """
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')

    try:
        # Count stocks at 60-day high/low using a JOIN instead of correlated subqueries
        rows = execute_query("""
            SELECT
                SUM(CASE WHEN a.close_price >= hist.high_60d THEN 1 ELSE 0 END) AS new_high,
                SUM(CASE WHEN a.close_price <= hist.low_60d THEN 1 ELSE 0 END) AS new_low
            FROM trade_stock_daily a
            INNER JOIN (
                SELECT stock_code,
                       MAX(high_price) AS high_60d,
                       MIN(low_price) AS low_60d
                FROM trade_stock_daily
                WHERE trade_date BETWEEN DATE_SUB(%s, INTERVAL 60 DAY)
                                     AND DATE_SUB(%s, INTERVAL 1 DAY)
                GROUP BY stock_code
            ) hist ON a.stock_code = hist.stock_code
            WHERE a.trade_date = %s
              AND a.close_price > 0
        """, (trade_date, trade_date, trade_date))

        if rows and rows[0]:
            new_high = int(rows[0]['new_high'] or 0)
            new_low = int(rows[0]['new_low'] or 0)
            _save(trade_date, 'new_high_60d', new_high, env=env)
            _save(trade_date, 'new_low_60d', new_low, env=env)
            logger.info("New 60d high: %d, low: %d", new_high, new_low)
    except Exception as e:
        logger.error("fetch_new_high_low failed: %s", e)


def fetch_all(trade_date: str = None, env: str = 'online'):
    """
    Run all fetchers for a single trade date.
    Call this in the daily scheduler after market close.
    """
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')

    logger.info("=== Market Dashboard Fetch: %s (env=%s) ===", trade_date, env)

    fetch_market_volume(trade_date, env=env)
    fetch_advance_decline(trade_date, env=env)
    fetch_limit_up_down(trade_date, env=env)
    fetch_margin_data(trade_date, env=env)
    fetch_new_high_low(trade_date, env=env)

    logger.info("=== Market Dashboard Fetch Complete ===")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    parser = argparse.ArgumentParser(description='Fetch market dashboard indicators')
    parser.add_argument('--date', help='Trade date (YYYY-MM-DD)')
    parser.add_argument('--env', default='online', help='DB environment')
    args = parser.parse_args()

    fetch_all(trade_date=args.date, env=args.env)
