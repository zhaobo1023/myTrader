# -*- coding: utf-8 -*-
"""
Hard-tech factor calculator

Factors:
  - rd_intensity:      rd_expense / abs(operating_revenue)
  - rd_growth:         rd_expense YoY growth (pct)
  - gross_margin_trend: gross_margin QoQ change (from extended_factor)
  - rd_efficiency:     revenue_growth / rd_intensity

Phase 1: Uses AKShare (Sina) to fetch rd_expense from income statements
Phase 2: gross_margin_trend from trade_stock_extended_factor

Usage:
  # Fetch rd_expense from Sina and calculate all factors
  python data_analyst/factors/hardtech_factor_calculator.py --fetch-rd

  # Calculate factors from existing data (no network call)
  python data_analyst/factors/hardtech_factor_calculator.py

  # Backfill gross_margin_trend only (from extended_factor history)
  python data_analyst/factors/hardtech_factor_calculator.py --backfill --start 2024-01-01
"""
import sys
import os
import gc
import time
import pandas as pd
import numpy as np
from datetime import date, timedelta
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, get_connection, get_dual_connections, dual_executemany

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500
TARGET_TABLE = 'trade_stock_hardtech_factor'

# Hard-tech industries for targeted rd_expense fetching
HARD_TECH_INDUSTRIES = [
    '电子', '计算机', '通信', '电力设备',
    '机械设备', '国防军工', '医药生物', '汽车',
    '有色金属', '化工',
]


def _to_full_code(code):
    """002636 -> 002636.SZ, 600036 -> 600036.SH"""
    if '.' in code:
        return code
    suffix = 'SH' if code.startswith('6') else 'SZ'
    return f"{code}.{suffix}"


def _to_bare_code(code):
    """002636.SZ -> 002636"""
    return code.split('.')[0]


def get_hardtech_stock_codes():
    """Get stock codes for hard-tech industries."""
    placeholders = ', '.join(['%s'] * len(HARD_TECH_INDUSTRIES))
    sql = f"""
        SELECT DISTINCT SUBSTRING_INDEX(stock_code, '.', 1) as bare_code,
               stock_code
        FROM trade_stock_basic
        WHERE industry IN ({placeholders})
    """
    rows = execute_query(sql, HARD_TECH_INDUSTRIES)
    if not rows:
        # Fallback: also add 688xxx (KCB) and 300xxx (CYB)
        sql2 = """
            SELECT DISTINCT SUBSTRING_INDEX(stock_code, '.', 1) as bare_code,
                   stock_code
            FROM trade_stock_basic
            WHERE stock_code LIKE '688%%' OR stock_code LIKE '300%%'
        """
        rows = execute_query(sql2)
    return [(r['bare_code'], r['stock_code']) for r in rows]


# ========================================================================
# Phase 1: Fetch rd_expense from Sina via AKShare
# ========================================================================

def fetch_and_save_rd_expense(stock_codes_bare, delay=0.3, batch_save=50):
    """
    Fetch rd_expense from Sina income statement and save to DB in batches.

    Args:
        stock_codes_bare: list of bare stock codes
        delay: seconds between requests
        batch_save: save to DB every N stocks
    """
    import akshare as ak

    upsert_sql = """
        INSERT INTO financial_income_detail
            (stock_code, report_date, rd_expense, operating_revenue, operating_cost)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            rd_expense = VALUES(rd_expense),
            operating_revenue = VALUES(operating_revenue),
            operating_cost = VALUES(operating_cost)
    """

    total = len(stock_codes_bare)
    pending = []
    total_saved = 0

    for i, code in enumerate(stock_codes_bare):
        try:
            df = ak.stock_financial_report_sina(stock=code, symbol='利润表')
            if df is None or df.empty:
                continue

            rd_col = [c for c in df.columns if '研发费用' in c]
            rev_col = [c for c in df.columns if '营业收入' in c and '总' not in c and '利息' not in c]
            cost_col = [c for c in df.columns if '营业成本' in c and '总' not in c and '税' not in c and '其他' not in c]
            date_col = '报告日' if '报告日' in df.columns else None

            if not rd_col or not rev_col or not date_col:
                continue

            rd_col = rd_col[0]
            rev_col = rev_col[0]
            cost_col = cost_col[0] if cost_col else None

            for _, row in df.head(8).iterrows():
                rd = pd.to_numeric(row.get(rd_col), errors='coerce')
                rev = pd.to_numeric(row.get(rev_col), errors='coerce')
                cost = pd.to_numeric(row.get(cost_col), errors='coerce') if cost_col else np.nan
                report_date = str(row.get(date_col, ''))

                if pd.isna(rd) or pd.isna(rev):
                    continue

                # Format date: '20260331' -> '2026-03-31'
                if len(report_date) == 8:
                    formatted = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:8]}"
                else:
                    continue

                pending.append((code, formatted, float(rd), float(rev), float(cost) if pd.notna(cost) else None))

        except Exception as e:
            if i < 5:
                logger.warning(f"  {code}: failed - {str(e)[:60]}")
            continue

        # Save batch
        if (i + 1) % batch_save == 0 or i == total - 1:
            if pending:
                conn = get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.executemany(upsert_sql, pending)
                    conn.commit()
                    total_saved += len(pending)
                    cursor.close()
                finally:
                    conn.close()
                logger.info(f"  Fetched {i+1}/{total} stocks, saved {total_saved} rows so far")
                pending = []

        time.sleep(delay)

    logger.info(f"Fetch complete: {total_saved} rd_expense rows saved")
    return total_saved


def save_rd_expense_to_db(df):
    """Save fetched rd_expense data to financial_income_detail table."""
    if df.empty:
        logger.warning("No rd_expense data to save")
        return 0

    upsert_sql = """
        INSERT INTO financial_income_detail
            (stock_code, report_date, rd_expense, operating_revenue, operating_cost)
        VALUES
            (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            rd_expense = VALUES(rd_expense),
            operating_revenue = VALUES(operating_revenue),
            operating_cost = VALUES(operating_cost)
    """

    rows_to_insert = []
    for _, row in df.iterrows():
        # Convert report_date format: '20260331' -> '2026-03-31'
        rd = str(row['report_date'])
        if len(rd) == 8:
            formatted = f"{rd[:4]}-{rd[4:6]}-{rd[6:8]}"
        else:
            continue

        rows_to_insert.append((
            row['stock_code'],
            formatted,
            row['rd_expense'],
            row['revenue'],
            row.get('cost'),
        ))

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executemany(upsert_sql, rows_to_insert)
        conn.commit()
        written = cursor.rowcount
        cursor.close()
    finally:
        conn.close()

    logger.info(f"Saved {len(rows_to_insert)} rd_expense rows to financial_income_detail")
    return len(rows_to_insert)


# ========================================================================
# Phase 2: Calculate factors from available data
# ========================================================================

def calc_factors_from_extended(start_date, end_date=None):
    """
    Calculate gross_margin_trend from trade_stock_extended_factor.

    This does NOT require rd_expense data. Uses the existing gross_margin
    time series from trade_stock_extended_factor to compute QoQ change.
    """
    if end_date is None:
        end_date = date.today().strftime('%Y-%m-%d')

    logger.info(f"Calculating gross_margin_trend from extended_factor: {start_date} ~ {end_date}")

    # Get trading dates
    sql = f"""
        SELECT DISTINCT calc_date FROM trade_stock_extended_factor
        WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
          AND gross_margin IS NOT NULL
        ORDER BY calc_date
    """
    rows = execute_query(sql)
    if not rows:
        logger.error("No dates with gross_margin data")
        return 0

    all_dates = [str(r['calc_date']) for r in rows]
    # Sample monthly
    sampled = all_dates[::20]
    if all_dates[-1] not in sampled:
        sampled.append(all_dates[-1])

    logger.info(f"  {len(sampled)} monthly dates to process")

    total_saved = 0
    for dt in sampled:
        # Load gross_margin for this date and previous quarter (~60 trading days earlier)
        # Find a date roughly 1 quarter back
        dt_idx = all_dates.index(dt) if dt in all_dates else len(all_dates) - 1
        prev_idx = max(0, dt_idx - 60)  # ~1 quarter back
        prev_dt = all_dates[prev_idx]

        sql_cur = f"""
            SELECT stock_code, gross_margin, revenue_growth
            FROM trade_stock_extended_factor
            WHERE calc_date = '{dt}' AND gross_margin IS NOT NULL
        """
        sql_prev = f"""
            SELECT stock_code, gross_margin
            FROM trade_stock_extended_factor
            WHERE calc_date = '{prev_dt}' AND gross_margin IS NOT NULL
        """

        cur_rows = execute_query(sql_cur)
        prev_rows = execute_query(sql_prev)

        if not cur_rows:
            continue

        # Build lookup for previous gross_margin
        prev_gm = {r['stock_code']: float(r['gross_margin']) for r in prev_rows if r['gross_margin']}

        # Calculate trend and save
        upsert_sql = f"""
            INSERT INTO {TARGET_TABLE}
                (stock_code, calc_date, gross_margin_trend)
            VALUES
                (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                gross_margin_trend = VALUES(gross_margin_trend)
        """

        rows_to_insert = []
        for r in cur_rows:
            code = r['stock_code']
            cur_gm = float(r['gross_margin']) if r['gross_margin'] else None
            if cur_gm is None:
                continue
            p_gm = prev_gm.get(code)
            if p_gm is not None:
                trend = cur_gm - p_gm
                rows_to_insert.append((code, dt, trend))

        if rows_to_insert:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany(upsert_sql, rows_to_insert)
                conn.commit()
                total_saved += len(rows_to_insert)
                cursor.close()
            finally:
                conn.close()

    logger.info(f"  Saved {total_saved} gross_margin_trend rows")
    return total_saved


def calc_rd_factors():
    """
    Calculate rd_intensity, rd_growth, rd_efficiency from financial_income_detail.

    Requires rd_expense data to be populated first (via --fetch-rd).
    """
    logger.info("Calculating rd factors from financial_income_detail...")

    # Load all stocks with rd_expense data
    sql = """
        SELECT stock_code, report_date, rd_expense, operating_revenue
        FROM financial_income_detail
        WHERE rd_expense IS NOT NULL AND operating_revenue IS NOT NULL
        ORDER BY stock_code, report_date ASC
    """
    rows = execute_query(sql)

    if not rows:
        logger.warning("No rd_expense data in financial_income_detail. Run --fetch-rd first.")
        return 0

    df = pd.DataFrame(rows)
    df['report_date'] = pd.to_datetime(df['report_date'])
    df['rd_expense'] = pd.to_numeric(df['rd_expense'], errors='coerce')
    df['operating_revenue'] = pd.to_numeric(df['operating_revenue'], errors='coerce')

    logger.info(f"  Loaded {len(df)} rows, {df['stock_code'].nunique()} stocks with rd_expense")

    # Load latest revenue_growth from extended_factor for rd_efficiency
    ext_sql = """
        SELECT stock_code, calc_date, revenue_growth
        FROM trade_stock_extended_factor
        WHERE revenue_growth IS NOT NULL
        ORDER BY stock_code, calc_date DESC
    """
    ext_rows = execute_query(ext_sql)
    ext_df = pd.DataFrame(ext_rows) if ext_rows else pd.DataFrame()

    if not ext_df.empty:
        ext_df['revenue_growth'] = pd.to_numeric(ext_df['revenue_growth'], errors='coerce')
        # Get latest revenue_growth per stock
        latest_rg = ext_df.sort_values('calc_date').groupby('stock_code').last()['revenue_growth'].to_dict()
    else:
        latest_rg = {}

    # Calculate factors per stock
    calc_date = date.today().strftime('%Y-%m-%d')
    results = []

    for code, group in df.groupby('stock_code'):
        group = group.sort_values('report_date').reset_index(drop=True)
        if len(group) < 1:
            continue

        latest = group.iloc[-1]
        rd = latest['rd_expense']
        rev = latest['operating_revenue']
        report_date = latest['report_date']

        # rd_intensity
        rd_intensity = np.nan
        if pd.notna(rd) and pd.notna(rev) and abs(rev) > 0:
            rd_intensity = rd / abs(rev)

        # rd_growth (YoY: compare to 4 quarters back)
        rd_growth = np.nan
        if pd.notna(rd) and len(group) >= 5:
            prev_y = group.iloc[-5]['rd_expense']
            if pd.notna(prev_y) and abs(prev_y) > 0:
                rd_growth = (rd - prev_y) / abs(prev_y) * 100

        # rd_efficiency
        code_full = _to_full_code(code)
        rg = latest_rg.get(code_full)
        rd_efficiency = np.nan
        if pd.notna(rd_intensity) and rd_intensity > 0 and pd.notna(rg):
            rd_efficiency = rg / rd_intensity

        results.append((
            code_full,
            calc_date,
            rd_intensity if pd.notna(rd_intensity) else None,
            rd_growth if pd.notna(rd_growth) else None,
            rd_efficiency if pd.notna(rd_efficiency) else None,
            None,  # gross_margin_trend (calculated separately)
            float(rd) if pd.notna(rd) else None,
            report_date.strftime('%Y-%m-%d') if isinstance(report_date, pd.Timestamp) else str(report_date),
        ))

    if not results:
        return 0

    # Save
    upsert_sql = f"""
        INSERT INTO {TARGET_TABLE}
            (stock_code, calc_date, rd_intensity, rd_growth, rd_efficiency,
             gross_margin_trend, rd_expense, report_date_used)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            rd_intensity = VALUES(rd_intensity),
            rd_growth = VALUES(rd_growth),
            rd_efficiency = VALUES(rd_efficiency),
            rd_expense = VALUES(rd_expense),
            report_date_used = VALUES(report_date_used)
    """

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executemany(upsert_sql, results)
        conn.commit()
        written = len(results)
        cursor.close()
    finally:
        conn.close()

    logger.info(f"  Saved {written} rows with rd factors")
    return written


# ========================================================================
# Main entry point
# ========================================================================

def main():
    parser = argparse.ArgumentParser(description='Hard-tech Factor Calculator')
    parser.add_argument('--fetch-rd', action='store_true',
                        help='Fetch rd_expense from Sina for hard-tech stocks')
    parser.add_argument('--calc-rd', action='store_true',
                        help='Calculate rd factors from existing data')
    parser.add_argument('--backfill', action='store_true',
                        help='Backfill gross_margin_trend from extended_factor')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--all', action='store_true',
                        help='Run all steps: fetch-rd + calc-rd + backfill')
    args = parser.parse_args()

    if args.all or args.fetch_rd:
        logger.info("Step 1: Fetching rd_expense from Sina...")
        codes = get_hardtech_stock_codes()
        bare_codes = [c[0] for c in codes]
        logger.info(f"  {len(bare_codes)} hard-tech stocks to fetch")
        fetch_and_save_rd_expense(bare_codes)

    if args.all or args.calc_rd:
        logger.info("Step 2: Calculating rd factors...")
        calc_rd_factors()

    if args.all or args.backfill:
        start = args.start or '2024-01-01'
        logger.info("Step 3: Backfilling gross_margin_trend...")
        calc_factors_from_extended(start, args.end)

    if not any([args.fetch_rd, args.calc_rd, args.backfill, args.all]):
        # Default: calculate rd factors from existing data
        logger.info("Default: calculating rd factors from existing data...")
        calc_rd_factors()
        calc_factors_from_extended(
            args.start or (date.today() - timedelta(days=180)).strftime('%Y-%m-%d')
        )


if __name__ == '__main__':
    main()
