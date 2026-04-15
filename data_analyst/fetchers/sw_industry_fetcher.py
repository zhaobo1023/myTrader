# -*- coding: utf-8 -*-
"""
申万行业分类抓取器

从 AKShare 拉取申万二级行业成分股，写入 trade_stock_basic 的
sw_level1 / sw_level2 字段。

数据来源：
- index_component_sw(801xxx): 返回各二级行业的成分股（6位裸码）
- sw_index_third_info: 提供完整的二级行业名称列表（通过 '上级行业' 字段）
- trade_stock_basic.industry: 已有的一级行业字段，用于推导 level2 -> level1 归属

用法:
    python -m data_analyst.fetchers.sw_industry_fetcher
    python -m data_analyst.fetchers.sw_industry_fetcher --dry-run
"""
import logging
import sys
import os
import time
import argparse
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.sw_industry_fetcher')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)




def fetch_sw_mapping() -> dict:
    """
    Scan 801xxx range, call index_component_sw for each valid code, and build:
      { bare_code: (level1_name, level2_name) }

    Level1 and Level2 names come from sw_index_second_info() which provides
    a direct mapping from 801xxx index codes to (L2 name, L1 parent name).
    No dependency on trade_stock_basic.industry column.
    """
    import akshare as ak

    # Build a direct mapping: 801xxx -> (l2_name, l1_name) from sw_index_second_info
    # This is the authoritative source and requires no DB data to work.
    code_to_names: dict = {}  # '801016' -> ('种植业', '农林牧渔')
    try:
        df2 = ak.sw_index_second_info()
        for _, row in df2.iterrows():
            raw_code = str(row['行业代码'])
            bare_idx = raw_code.replace('.SI', '').strip()
            l2_name = str(row['行业名称']).strip()
            l1_name = str(row['上级行业']).strip()
            code_to_names[bare_idx] = (l2_name, l1_name)
        logger.info('Loaded %d L2 index mappings from sw_index_second_info', len(code_to_names))
    except Exception as e:
        logger.error('sw_index_second_info failed: %s', e)
        return {}

    stock_map: dict = {}  # bare_code -> (level1, level2)

    logger.info('Scanning %d SW level2 codes from sw_index_second_info...', len(code_to_names))

    for code, (l2_name, l1_name) in code_to_names.items():

        try:
            df = ak.index_component_sw(symbol=code)
            if df.empty or '证券代码' not in df.columns:
                continue

            stocks = [str(c) for c in df['证券代码'].tolist()]
            if not stocks:
                continue

            for bare in stocks:
                stock_map[bare] = (l1_name, l2_name)

            logger.debug('Code %s (%s/%s): %d stocks', code, l1_name, l2_name, len(stocks))

        except Exception as e:
            logger.debug('Code %s: error %s', code, e)

        time.sleep(0.15)

    logger.info('Final stock mapping: %d stocks', len(stock_map))
    return stock_map


def sync_to_db(stock_map: dict, dry_run: bool = False) -> dict:
    """
    将 stock_map 写入 trade_stock_basic 的 sw_level1 / sw_level2 字段。
    只更新已存在于 trade_stock_basic 的股票。

    Returns: {updated, skipped, total}
    """
    rows = list(execute_query(
        'SELECT stock_code FROM trade_stock_basic',
        (),
        env='online',
    ))
    existing_bare = set()
    for r in rows:
        code = r['stock_code']
        bare = code.split('.')[0] if '.' in code else code
        existing_bare.add(bare)

    updated = 0
    skipped = 0

    for bare_code, (level1, level2) in stock_map.items():
        if bare_code not in existing_bare:
            skipped += 1
            continue

        if dry_run:
            logger.debug('[dry-run] %s -> %s / %s', bare_code, level1, level2)
            updated += 1
            continue

        execute_update(
            """
            UPDATE trade_stock_basic
            SET sw_level1 = %s, sw_level2 = %s
            WHERE stock_code LIKE %s
            """,
            (level1, level2, bare_code + '%'),
            env='online',
        )
        updated += 1

    stats = {'updated': updated, 'skipped': skipped, 'total': len(stock_map)}
    logger.info('DB sync complete: updated=%d skipped=%d total_mapped=%d',
                updated, skipped, len(stock_map))
    return stats


def run(dry_run: bool = False) -> dict:
    """Main entry: fetch + sync."""
    logger.info('=== 申万行业分类抓取开始 (dry_run=%s) ===', dry_run)
    stock_map = fetch_sw_mapping()
    stats = sync_to_db(stock_map, dry_run=dry_run)
    logger.info('=== 申万行业分类抓取完成 ===')
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='抓取申万行业分类并写入数据库')
    parser.add_argument('--dry-run', action='store_true', help='仅统计，不写库')
    args = parser.parse_args()
    result = run(dry_run=args.dry_run)
    print(result)
