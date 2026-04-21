# -*- coding: utf-8 -*-
"""
Daily Basic dv_ttm Fetcher

Fetches dv_ttm (dividend yield TTM) for all A-share stocks and writes to
trade_stock_daily_basic.dv_ttm.

Two modes:
  1. Tushare daily_basic API (requires 120+ points, preferred)
  2. Tushare dividend API (free tier) -- calculates dv_ttm from dividend
     history + close price in DB.

Usage:
    python data_analyst/fetchers/daily_basic_fetcher.py
    python data_analyst/fetchers/daily_basic_fetcher.py --start 20250101
    python data_analyst/fetchers/daily_basic_fetcher.py --method dividend

Environment: TUSHARE_TOKEN in .env
"""
import sys
import os
import time
import argparse
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.db import get_connection, execute_query, get_dual_connections, dual_executemany
from config.settings import TUSHARE_TOKEN

try:
    import tushare as ts
    HAS_TUSHARE = True
except ImportError:
    HAS_TUSHARE = False

REQUEST_DELAY = 0.35

# ============================================================
# Tushare API
# ============================================================

_pro = None


def get_pro():
    global _pro
    if _pro is not None:
        return _pro
    token = TUSHARE_TOKEN
    if not token:
        raise RuntimeError("TUSHARE_TOKEN not configured")
    ts.set_token(token)
    _pro = ts.pro_api()
    return _pro


# ============================================================
# Mode 1: daily_basic API (bulk, one call per date)
# ============================================================

def _daily_basic_available() -> bool:
    """Check if daily_basic API is accessible."""
    pro = get_pro()
    try:
        pro.daily_basic(trade_date='20990101', fields='ts_code', limit=1)
        return True
    except Exception:
        return False


def _fetch_daily_basic_bulk(start_date: str, end_date: str):
    """Fetch all dates using daily_basic API."""
    pro = get_pro()
    df_cal = pro.trade_cal(
        exchange='SSE', start_date=start_date, end_date=end_date,
        is_open='1', fields='cal_date',
    )
    trade_dates = df_cal['cal_date'].tolist()

    existing = _get_existing_dates()
    pending = [d for d in trade_dates if d not in existing]
    print(f"  {len(trade_dates)} trading dates, {len(pending)} pending")

    total = 0
    for i, td in enumerate(pending, 1):
        print(f"\r  [{i}/{len(pending)}] {td}...", end='', flush=True)
        try:
            time.sleep(REQUEST_DELAY)
            df = pro.daily_basic(
                trade_date=td,
                fields='ts_code,trade_date,turnover_rate,pe_ttm,pb,ps_ttm,'
                       'dv_ttm,total_mv,circ_mv,total_share,circ_share,free_share',
            )
            if df is not None and not df.empty:
                _save_daily_basic_df(df)
                total += len(df)
                print(f"\r  [{i}/{len(pending)}] {td}: {len(df):,} rows")
            else:
                print(f"\r  [{i}/{len(pending)}] {td}: 0 rows")
        except Exception as e:
            print(f"\r  [{i}/{len(pending)}] {td}: FAILED - {e}")

    return total


# ============================================================
# Mode 2: dividend API + DB price (per-stock, calculates dv_ttm)
# ============================================================

def _fetch_dividend_dv_ttm(start_date: str, end_date: str):
    """
    Calculate dv_ttm from Tushare dividend data + DB close prices.

    Logic:
      1. Get all stock codes from DB
      2. For each stock, fetch dividend history from Tushare
      3. For each trade date in range, sum cash_div of dividends with ex_date
         in the past 365 days -> annual dividend
      4. dv_ttm = annual_dividend / close_price * 100
      5. UPDATE trade_stock_daily_basic SET dv_ttm = ...
    """
    pro = get_pro()

    # Get stock codes
    rows = execute_query("SELECT DISTINCT stock_code FROM trade_stock_daily_basic")
    stock_codes = [r['stock_code'] for r in rows]
    print(f"  {len(stock_codes)} stocks to process")

    # Get close prices from trade_stock_daily for the date range
    conn = get_connection()
    price_df = pd.read_sql(f"""
        SELECT stock_code, trade_date, close_price
        FROM trade_stock_daily
        WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}'
    """, conn)
    conn.close()
    price_df['trade_date'] = pd.to_datetime(price_df['trade_date'])
    price_df['close_price'] = pd.to_numeric(price_df['close_price'], errors='coerce')

    total_updated = 0
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)

    for i, ts_code in enumerate(stock_codes, 1):
        if i % 50 == 0:
            print(f"\r  Progress: {i}/{len(stock_codes)} ({total_updated} rows updated)", end='', flush=True)
        try:
            time.sleep(REQUEST_DELAY)
            div_df = pro.dividend(
                ts_code=ts_code,
                fields='ts_code,ex_date,cash_div',
            )
            if div_df is None or div_df.empty:
                continue

            div_df = div_df[div_df['ex_date'].notna() & (div_df['cash_div'] > 0)].copy()
            div_df['ex_date'] = pd.to_datetime(div_df['ex_date'])

            # Get price data for this stock
            stock_prices = price_df[price_df['stock_code'] == ts_code].copy()
            if stock_prices.empty:
                continue

            # For each trade date, calculate TTM dividend sum
            updates = []
            for _, row in stock_prices.iterrows():
                td = row['trade_date']
                close = row['close_price']
                if pd.isna(close) or close <= 0:
                    continue

                # Sum dividends with ex_date in (td - 365d, td]
                mask = (div_df['ex_date'] > td - pd.Timedelta(days=365)) & (div_df['ex_date'] <= td)
                annual_div = div_df.loc[mask, 'cash_div'].sum()  # per 10 shares
                if annual_div <= 0:
                    continue

                # dv_ttm = (annual_div_per_share / close_price) * 100
                # cash_div is per 10 shares, so per share = cash_div / 10
                dv = (annual_div / 10.0) / close * 100.0
                updates.append((dv, ts_code, td.strftime('%Y-%m-%d')))

            if updates:
                _bulk_update_dv_ttm(updates)
                total_updated += len(updates)

        except Exception as e:
            pass  # Skip failed stocks silently

    print(f"\r  Progress: {len(stock_codes)}/{len(stock_codes)} ({total_updated} rows updated)")
    return total_updated


def _bulk_update_dv_ttm(updates: list):
    """Bulk UPDATE dv_ttm for (value, stock_code, trade_date) tuples."""
    if not updates:
        return
    conn, conn2 = get_dual_connections()
    try:
        sql = "UPDATE trade_stock_daily_basic SET dv_ttm = %s WHERE stock_code = %s AND trade_date = %s"
        dual_executemany(conn, conn2, sql, updates)
    finally:
        conn.close()


# ============================================================
# Common helpers
# ============================================================

INSERT_SQL = """
    INSERT INTO trade_stock_daily_basic
    (stock_code, trade_date, total_mv, circ_mv, pe_ttm, pb, ps_ttm, dv_ttm,
     total_share, circ_share, turnover_rate, free_share)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    total_mv=VALUES(total_mv), circ_mv=VALUES(circ_mv),
    pe_ttm=VALUES(pe_ttm), pb=VALUES(pb), ps_ttm=VALUES(ps_ttm), dv_ttm=VALUES(dv_ttm),
    total_share=VALUES(total_share), circ_share=VALUES(circ_share),
    turnover_rate=VALUES(turnover_rate), free_share=VALUES(free_share)
"""


def _save_daily_basic_df(df: pd.DataFrame):
    """Save daily_basic DataFrame to DB."""
    records = []
    for _, row in df.iterrows():
        stock_code = row['ts_code']
        records.append((
            stock_code,
            pd.to_datetime(row['trade_date']).strftime('%Y-%m-%d'),
            float(row['total_mv']) if pd.notna(row.get('total_mv')) else None,
            float(row['circ_mv']) if pd.notna(row.get('circ_mv')) else None,
            float(row['pe_ttm']) if pd.notna(row.get('pe_ttm')) else None,
            float(row['pb']) if pd.notna(row.get('pb')) else None,
            float(row['ps_ttm']) if pd.notna(row.get('ps_ttm')) else None,
            float(row['dv_ttm']) if pd.notna(row.get('dv_ttm')) else None,
            float(row['total_share']) if pd.notna(row.get('total_share')) else None,
            float(row['circ_share']) if pd.notna(row.get('circ_share')) else None,
            float(row['turnover_rate']) if pd.notna(row.get('turnover_rate')) else None,
            float(row['free_share']) if pd.notna(row.get('free_share')) else None,
        ))
    if records:
        conn, conn2 = get_dual_connections()
        try:
            dual_executemany(conn, conn2, INSERT_SQL, records)
        finally:
            conn.close()


def _get_existing_dates() -> set:
    rows = execute_query("SELECT DISTINCT trade_date FROM trade_stock_daily_basic")
    return {r['trade_date'].strftime('%Y%m%d') for r in rows if r['trade_date']}


def _print_summary():
    summary = execute_query("""
        SELECT COUNT(DISTINCT stock_code) as stock_cnt,
               COUNT(*) as row_cnt,
               MIN(trade_date) as min_date, MAX(trade_date) as max_date
        FROM trade_stock_daily_basic
    """)
    if summary:
        row = summary[0]
        print(f"\nDB trade_stock_daily_basic overview:")
        print(f"  {row['stock_cnt']} stocks, {row['row_cnt']:,} rows")
        print(f"  Date range: {row['min_date']} ~ {row['max_date']}")

    dv_summary = execute_query("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN dv_ttm IS NOT NULL AND dv_ttm > 0 THEN 1 ELSE 0 END) as has_dv
        FROM trade_stock_daily_basic
        WHERE trade_date = (SELECT MAX(trade_date) FROM trade_stock_daily_basic)
    """)
    if dv_summary:
        row = dv_summary[0]
        print(f"  dv_ttm coverage (latest date): {row['has_dv']}/{row['total']}")
    print("=" * 60)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Fetch dv_ttm into trade_stock_daily_basic')
    parser.add_argument('--start', type=str, default=None,
                        help='Start date YYYYMMDD (default: 365 days ago)')
    parser.add_argument('--end', type=str, default=None,
                        help='End date YYYYMMDD (default: today)')
    parser.add_argument('--method', type=str, default='auto', choices=['auto', 'daily_basic', 'dividend'],
                        help='Fetch method: auto, daily_basic, or dividend')
    args = parser.parse_args()

    print("=" * 60)
    print("dv_ttm Fetcher (Tushare -> MySQL)")
    print("=" * 60)

    if not HAS_TUSHARE or not TUSHARE_TOKEN:
        print("\nError: Tushare not installed or TUSHARE_TOKEN not configured")
        return

    start = args.start or (date.today() - timedelta(days=365)).strftime('%Y%m%d')
    end = args.end or date.today().strftime('%Y%m%d')
    print(f"\nDate range: {start} ~ {end}")

    # Determine method
    method = args.method
    if method == 'auto':
        print("Checking daily_basic API access...")
        if _daily_basic_available():
            print("  daily_basic API available, using bulk mode")
            method = 'daily_basic'
        else:
            print("  daily_basic API not available (needs 120+ points), using dividend mode")
            method = 'dividend'

    t0 = time.time()
    if method == 'daily_basic':
        total = _fetch_daily_basic_bulk(start, end)
    else:
        total = _fetch_dividend_dv_ttm(start, end)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"Done! {total:,} rows, {elapsed:.1f}s")
    _print_summary()


if __name__ == "__main__":
    main()
