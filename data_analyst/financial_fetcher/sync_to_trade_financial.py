# -*- coding: utf-8 -*-
"""
Sync financial_income + financial_balance -> trade_stock_financial

Merges the two tables by (stock_code, report_date) and upserts into
trade_stock_financial, which is what the five-section research pipeline reads.

Usage:
    python -m data_analyst.financial_fetcher.sync_to_trade_financial
    python -m data_analyst.financial_fetcher.sync_to_trade_financial --env online
"""

import logging
import sys
import os
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.db import execute_query, get_dual_connections, dual_executemany

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO trade_stock_financial
    (stock_code, report_date, revenue, net_profit, eps, roe,
     gross_margin, total_assets, total_equity, data_source)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    revenue        = VALUES(revenue),
    net_profit     = VALUES(net_profit),
    eps            = VALUES(eps),
    roe            = VALUES(roe),
    gross_margin   = VALUES(gross_margin),
    total_assets   = VALUES(total_assets),
    total_equity   = VALUES(total_equity),
    data_source    = VALUES(data_source)
"""


def _to_full_code(code: str) -> str:
    """002636 -> 002636.SZ, 600036 -> 600036.SH"""
    if '.' in code:
        return code
    suffix = 'SH' if code.startswith('6') else 'SZ'
    return f"{code}.{suffix}"


def sync(env: str = 'online', batch_size: int = 5000):
    logger.info(f"Syncing financial_income + financial_balance -> trade_stock_financial ({env})")

    # Pull all income rows
    logger.info("Loading financial_income ...")
    income_rows = execute_query(
        "SELECT stock_code, report_date, revenue, net_profit, eps, roe, gross_margin FROM financial_income",
        env=env,
    )
    logger.info(f"  {len(income_rows)} rows from financial_income")

    # Build income lookup: (code, date) -> row
    income_map = {}
    for r in income_rows:
        key = (r['stock_code'], str(r['report_date']))
        income_map[key] = r

    # Pull all balance rows
    logger.info("Loading financial_balance ...")
    balance_rows = execute_query(
        "SELECT stock_code, report_date, total_assets, total_equity FROM financial_balance",
        env=env,
    )
    logger.info(f"  {len(balance_rows)} rows from financial_balance")

    # Build balance lookup
    balance_map = {}
    for r in balance_rows:
        key = (r['stock_code'], str(r['report_date']))
        balance_map[key] = r

    # Merge: all keys from income (balance is supplementary)
    all_keys = set(income_map.keys()) | set(balance_map.keys())
    logger.info(f"Total unique (stock, date) pairs: {len(all_keys)}")

    records = []
    for (code, date_str) in all_keys:
        inc = income_map.get((code, date_str), {})
        bal = balance_map.get((code, date_str), {})

        full_code = _to_full_code(code)
        records.append((
            full_code,
            date_str,
            inc.get('revenue'),
            inc.get('net_profit'),
            inc.get('eps'),
            inc.get('roe'),
            inc.get('gross_margin'),
            bal.get('total_assets'),
            bal.get('total_equity'),
            'akshare',
        ))

    # Batch upsert with dual-write
    logger.info(f"Upserting {len(records)} rows in batches of {batch_size} ...")
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        conn, conn2 = get_dual_connections(primary_env=env)
        try:
            dual_executemany(conn, conn2, UPSERT_SQL, batch, _logger=logger)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        total += len(batch)
        logger.info(f"  {total}/{len(records)} done")

    logger.info(f"Sync complete. {total} rows upserted into trade_stock_financial.")

    # Verify
    rows = execute_query(
        "SELECT COUNT(*) as cnt, COUNT(DISTINCT stock_code) as stocks FROM trade_stock_financial",
        env=env,
    )
    logger.info(f"trade_stock_financial now: {rows[0]['cnt']} rows, {rows[0]['stocks']} stocks")


def main():
    parser = argparse.ArgumentParser(description='Sync financial_income/balance -> trade_stock_financial')
    parser.add_argument('--env', default='online', choices=['local', 'online'])
    parser.add_argument('--batch-size', type=int, default=5000)
    args = parser.parse_args()
    sync(env=args.env, batch_size=args.batch_size)


if __name__ == '__main__':
    main()
