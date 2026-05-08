#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetch rd_expense for 688 (KCB) stocks from Sina with robust timeout handling.
Saves every 30 stocks to avoid data loss on interruption.
"""
import sys
import os
import socket
import time
import logging
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import execute_query, get_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global timeout for all socket operations
socket.setdefaulttimeout(20)

UPSERT_SQL = """
    INSERT INTO financial_income_detail
        (stock_code, report_date, rd_expense, operating_revenue, operating_cost)
    VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        rd_expense = VALUES(rd_expense),
        operating_revenue = VALUES(operating_revenue),
        operating_cost = VALUES(operating_cost)
"""


def fetch_kcb_rd():
    import akshare as ak

    # Get all 688 bare codes needing data
    rows = execute_query('''
        SELECT DISTINCT SUBSTRING_INDEX(b.stock_code, ".", 1) as bare_code
        FROM trade_stock_basic b
        WHERE b.stock_code LIKE "688%%"
          AND b.industry IN ("电子","计算机","通信","电力设备","机械设备","国防军工","医药生物","汽车","有色金属","化工")
        ORDER BY bare_code
    ''')
    codes = [r['bare_code'] for r in rows]
    total = len(codes)
    logger.info(f"Total 688 stocks to fetch: {total}")

    pending = []
    total_saved = 0
    success = 0
    failed = 0

    for i, code in enumerate(codes):
        try:
            df = ak.stock_financial_report_sina(stock=code, symbol='利润表')
            if df is None or df.empty:
                failed += 1
                continue

            df = df.reset_index(drop=True)
            rd_col = [c for c in df.columns if '研发费用' in c]
            rev_col = [c for c in df.columns if '营业收入' in c and '总' not in c and '利息' not in c]
            cost_col = [c for c in df.columns if '营业成本' in c and '总' not in c and '税' not in c and '其他' not in c]
            date_col = '报告日' if '报告日' in df.columns else None

            if not rd_col or not rev_col or not date_col:
                failed += 1
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

                if len(report_date) == 8:
                    formatted = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:8]}"
                else:
                    continue

                pending.append((code, formatted, float(rd), float(rev),
                                float(cost) if pd.notna(cost) else None))

            success += 1

        except Exception as e:
            failed += 1
            if failed <= 5:
                logger.warning(f"  {code}: {str(e)[:60]}")

        # Save batch every 30 stocks
        if (i + 1) % 30 == 0 or i == total - 1:
            if pending:
                try:
                    conn = get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.executemany(UPSERT_SQL, pending)
                        conn.commit()
                        total_saved += len(pending)
                        cursor.close()
                    finally:
                        conn.close()
                except Exception as e:
                    logger.error(f"  DB save error: {e}")
            pending = []
            logger.info(f"  [{i+1}/{total}] success={success}, failed={failed}, saved={total_saved} rows")

        time.sleep(0.3)

    logger.info(f"Done! success={success}, failed={failed}, total_saved={total_saved}")


if __name__ == '__main__':
    fetch_kcb_rd()
