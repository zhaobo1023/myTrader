#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetch rd_expense and selling_expense for ALL A-share stocks from East Money.

Uses ak.stock_profit_sheet_by_report_em which returns detailed income statements
including RESEARCH_EXPENSE and SALE_EXPENSE columns.

Saves to financial_income_detail table every batch_size stocks.
Supports skip-existing, prefix filter, and resume via --skip N.

Usage:
    DB_ENV=online python scripts/fetch_all_rd_expense.py
    DB_ENV=online python scripts/fetch_all_rd_expense.py --skip-existing
    DB_ENV=online python scripts/fetch_all_rd_expense.py --prefix 600
    DB_ENV=online python scripts/fetch_all_rd_expense.py --skip 500
    DB_ENV=online python scripts/fetch_all_rd_expense.py --batch-size 20
"""
import sys
import os
import socket
import time
import logging
import argparse
from datetime import datetime

import akshare as ak

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import execute_query, get_connection  # noqa: E402
from data_analyst.financial_fetcher.fetcher import safe_float, _to_em_symbol  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

socket.setdefaulttimeout(20)

UPSERT_SQL = """
    INSERT INTO financial_income_detail
        (stock_code, report_date, operating_revenue, operating_cost,
         selling_expense, admin_expense, finance_expense,
         rd_expense, net_profit, rd_expense_ratio, source)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        operating_revenue = VALUES(operating_revenue),
        operating_cost = VALUES(operating_cost),
        selling_expense = VALUES(selling_expense),
        admin_expense = VALUES(admin_expense),
        finance_expense = VALUES(finance_expense),
        rd_expense = VALUES(rd_expense),
        net_profit = VALUES(net_profit),
        rd_expense_ratio = VALUES(rd_expense_ratio),
        source = VALUES(source)
"""


def get_all_stock_codes(skip_existing=True, prefix_filter=None):
    """Get all A-share bare stock codes from trade_stock_basic."""
    skip_join = ''
    if skip_existing:
        skip_join = """
            LEFT JOIN (
                SELECT DISTINCT stock_code FROM financial_income_detail
                WHERE rd_expense IS NOT NULL
            ) ex ON SUBSTRING_INDEX(b.stock_code, '.', 1) = ex.stock_code
        """
        skip_where = 'AND ex.stock_code IS NULL'
    else:
        skip_where = ''

    prefix_cond = ''
    if prefix_filter:
        prefix_cond = f"AND SUBSTRING_INDEX(b.stock_code, '.', 1) LIKE '{prefix_filter}%%'"

    sql = f"""
        SELECT DISTINCT SUBSTRING_INDEX(b.stock_code, '.', 1) AS bare_code
        FROM trade_stock_basic b
        {skip_join}
        WHERE b.is_st = 0
          {skip_where}
          {prefix_cond}
        ORDER BY bare_code
    """
    rows = execute_query(sql, env=os.environ.get('DB_ENV', 'online'))
    codes = [r['bare_code'] for r in rows]
    logger.info(f"Stocks to fetch: {len(codes)}")
    return codes


def fetch_one(code):
    """Fetch income detail for one stock from East Money.

    Returns list of tuples for UPSERT_SQL.
    """
    em_code = _to_em_symbol(code)
    try:
        df = ak.stock_profit_sheet_by_report_em(symbol=em_code)
    except Exception as e:
        logger.warning(f"  {code}: API failed - {str(e)[:80]}")
        return []

    if df is None or df.empty:
        return []

    rows = []
    for _, row in df.iterrows():
        raw = str(row.get("REPORT_DATE", ""))[:10]
        try:
            report_date = datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            continue

        revenue_raw = safe_float(row.get("OPERATE_INCOME"))
        cost_raw = safe_float(row.get("OPERATE_COST"))
        rd_raw = safe_float(row.get("RESEARCH_EXPENSE"))
        sell_raw = safe_float(row.get("SALE_EXPENSE"))
        admin_raw = safe_float(row.get("MANAGE_EXPENSE"))
        finance_raw = safe_float(row.get("FINANCE_EXPENSE"))
        net_profit_raw = safe_float(row.get("PARENT_NETPROFIT"))

        rd_ratio = None
        if rd_raw and revenue_raw and revenue_raw > 0:
            rd_ratio = round(rd_raw / revenue_raw * 100, 4)

        rows.append((
            code,
            report_date,
            round(revenue_raw / 1e8, 4) if revenue_raw else None,
            round(cost_raw / 1e8, 4) if cost_raw else None,
            round(sell_raw / 1e8, 4) if sell_raw else None,
            round(admin_raw / 1e8, 4) if admin_raw else None,
            round(finance_raw / 1e8, 4) if finance_raw else None,
            round(rd_raw / 1e8, 4) if rd_raw else None,
            round(net_profit_raw / 1e8, 4) if net_profit_raw else None,
            rd_ratio,
            'eastmoney',
        ))

    return rows


def main():
    parser = argparse.ArgumentParser(description='Fetch rd_expense for all A-shares')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip stocks that already have rd_expense data')
    parser.add_argument('--prefix', type=str, default=None,
                        help='Only fetch stocks with this code prefix (e.g. 600, 300)')
    parser.add_argument('--skip', type=int, default=0,
                        help='Skip first N stocks (for resume)')
    parser.add_argument('--batch-size', type=int, default=30,
                        help='Save to DB every N stocks')
    parser.add_argument('--delay', type=float, default=0.3,
                        help='Seconds between API requests')
    parser.add_argument('--env', type=str, default=None,
                        help='DB environment (default: DB_ENV or online)')
    args = parser.parse_args()

    env = args.env or os.environ.get('DB_ENV', 'online')
    os.environ['DB_ENV'] = env

    codes = get_all_stock_codes(skip_existing=args.skip_existing,
                                prefix_filter=args.prefix)
    if not codes:
        logger.info("No stocks to fetch. Done.")
        return

    total = len(codes)
    pending = []
    total_saved = 0
    total_rd = 0
    errors = 0

    for i, code in enumerate(codes):
        if i < args.skip:
            continue

        rows = fetch_one(code)
        if rows:
            rd_count = sum(1 for r in rows if r[7] is not None)
            total_rd += rd_count
            pending.extend(rows)
        else:
            errors += 1

        # Save batch with fresh connection to avoid timeout
        if (i + 1) % args.batch_size == 0 or i == total - 1:
            if pending:
                conn = get_connection(env=env)
                try:
                    cursor = conn.cursor()
                    cursor.executemany(UPSERT_SQL, pending)
                    conn.commit()
                    cursor.close()
                    total_saved += len(pending)
                    logger.info(f"  [{i+1}/{total}] saved {total_saved} rows "
                                f"({total_rd} with rd_expense), {errors} errors")
                    pending = []
                except Exception as e:
                    logger.error(f"  DB error at batch {i+1}: {e}")
                finally:
                    conn.close()

        if (i + 1) % 100 == 0:
            logger.info(f"  Progress: {i+1}/{total} stocks processed")

        time.sleep(args.delay)

    logger.info(f"Done. Total: {total_saved} rows saved, "
                f"{total_rd} with rd_expense, {errors} stocks had errors")


if __name__ == '__main__':
    main()
