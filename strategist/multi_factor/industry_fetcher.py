# -*- coding: utf-8 -*-
"""
行业分类数据抓取

从东方财富 datacenter API 批量获取所有股票的行业分类，写入 trade_stock_basic.industry 列。
数据源: RPT_F10_BASIC_ORGINFO.BOARD_NAME_LEVEL (东方财富行业板块三级分类)

Usage:
    python -m strategist.multi_factor.industry_fetcher
    python -m strategist.multi_factor.industry_fetcher --dry-run
"""

import argparse
import logging
import os
import sys
import time

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import get_connection, get_dual_connections

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
)
logger = logging.getLogger(__name__)

API_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
PAGE_SIZE = 5000
MAX_RETRIES = 3
RETRY_WAIT = 5


def fetch_all_industries() -> dict:
    """
    从东方财富 datacenter API 批量获取所有证券的行业分类。

    BOARD_NAME_LEVEL 格式: "银行-银行II-股份制银行III"
    取第一级 (如 "银行") 作为行业分类。

    Returns:
        dict {SECUCODE: industry_L1, ...}
            e.g. {"600015.SH": "银行", "000001.SZ": "银行", ...}
    """
    all_data = []
    page = 1

    # First request to get total count
    params = {
        'reportName': 'RPT_F10_BASIC_ORGINFO',
        'columns': 'SECUCODE,BOARD_NAME_LEVEL',
        'pageNumber': page,
        'pageSize': PAGE_SIZE,
        'sortTypes': -1,
        'sortColumns': 'SECUCODE',
    }

    done = False
    while not done:
        data = None
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.get(API_URL, params=params, timeout=30)
                d = r.json()

                if not d.get('success'):
                    msg = d.get('message', '')
                    if '频率' in msg:
                        logger.warning(f"Rate limited, waiting {RETRY_WAIT * (attempt+1)}s...")
                        time.sleep(RETRY_WAIT * (attempt + 1))
                        continue
                    logger.error(f"API error: {msg}")
                    done = True
                    break

                result = d.get('result', {})
                data = result.get('data', [])
                count = result.get('count', 0)

                if not data:
                    done = True
                    break

                all_data.extend(data)
                total_pages = (count + PAGE_SIZE - 1) // PAGE_SIZE
                logger.info(f"Page {page}/{total_pages}: {len(data)} records "
                            f"(total: {len(all_data)}/{count})")

                if len(all_data) >= count:
                    done = True
                    break

                page += 1
                params['pageNumber'] = page
                break

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Retry {attempt+1}/{MAX_RETRIES}: {e}")
                    time.sleep(RETRY_WAIT * (attempt + 1))
                    continue
                logger.error(f"Failed to fetch page {page}: {e}")
                done = True
                break

    # Parse: SECUCODE -> industry_L1
    industry_map = {}
    for row in all_data:
        secucode = row.get('SECUCODE', '')
        board = row.get('BOARD_NAME_LEVEL', '')
        if secucode and board:
            # Take first level: "银行-银行II-股份制银行III" -> "银行"
            industry_l1 = board.split('-')[0] if '-' in board else board
            industry_map[secucode] = industry_l1

    logger.info(f"Total: {len(industry_map)} stocks with industry classification")

    # Print distribution
    from collections import Counter
    dist = Counter(industry_map.values())
    logger.info(f"Industry distribution (top 20):")
    for ind, cnt in dist.most_common(20):
        logger.info(f"  {ind}: {cnt}")

    return industry_map


def update_db(industry_map: dict, dry_run: bool = False):
    """Update trade_stock_basic.industry column using batch UPDATE with CASE WHEN."""
    if dry_run:
        logger.info(f"[DRY RUN] Would update {len(industry_map)} rows")
        for code, ind in list(industry_map.items())[:10]:
            print(f"  {code}: {ind}")
        return

    conn = get_connection()
    conn2 = None
    try:
        _, conn2 = get_dual_connections()
    except Exception:
        pass

    try:
        cursor = conn.cursor()

        # Ensure column exists (IF NOT EXISTS not supported on older MySQL)
        try:
            cursor.execute("""
                ALTER TABLE trade_stock_basic
                ADD COLUMN industry VARCHAR(50) DEFAULT NULL
            """)
            conn.commit()
        except Exception:
            conn.rollback()
            logger.info("Column 'industry' already exists (skipped ALTER)")

        # Filter to only stocks that exist in our DB
        cursor.execute("SELECT stock_code FROM trade_stock_basic")
        db_codes = {row[0] for row in cursor.fetchall()}
        matched = {code: ind for code, ind in industry_map.items() if code in db_codes}
        logger.info(f"Matched {len(matched)}/{len(industry_map)} stocks in trade_stock_basic")

        if not matched:
            logger.warning("No matching stocks found")
            return

        # Build batch UPDATE with CASE WHEN (single query per batch)
        BATCH_SIZE = 500
        items = list(matched.items())
        total_updated = 0
        all_batches_sql = []  # collect for secondary write

        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i:i + BATCH_SIZE]
            case_parts = []
            params = []
            for code, ind in batch:
                case_parts.append("WHEN %s THEN %s")
                params.extend([code, ind])
            params.extend([code for code, _ in batch])  # WHERE IN codes

            sql = (
                f"UPDATE trade_stock_basic SET industry = CASE stock_code "
                f"{' '.join(case_parts)} "
                f"ELSE industry END "
                f"WHERE stock_code IN ({','.join(['%s'] * len(batch))})"
            )
            cursor.execute(sql, params)
            total_updated += cursor.rowcount
            all_batches_sql.append((sql, params))

            if (i + BATCH_SIZE) % 2000 == 0 or i + BATCH_SIZE >= len(items):
                logger.info(f"  batch progress: {min(i + BATCH_SIZE, len(items))}/{len(items)}")

        conn.commit()
        logger.info(f"DB updated: {total_updated} rows in trade_stock_basic.industry")
    finally:
        conn.close()

    # Dual-write to secondary (best-effort)
    if conn2:
        try:
            cursor2 = conn2.cursor()
            for sql, params in all_batches_sql:
                try:
                    cursor2.execute(sql, params)
                except Exception:
                    pass
            conn2.commit()
            cursor2.close()
        except Exception as e:
            logger.warning("Dual-write update_db failed: %s", e)
        finally:
            conn2.close()


def main():
    parser = argparse.ArgumentParser(description='Fetch industry classification for stocks')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only print results, do not write to DB')
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Industry Classification Fetcher")
    logger.info("=" * 50)

    # 1. Fetch all industries from East Money datacenter
    t0 = time.time()
    industry_map = fetch_all_industries()
    logger.info(f"Fetch completed in {time.time()-t0:.1f}s")

    # 2. Update DB
    update_db(industry_map, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
