# -*- coding: utf-8 -*-
"""
东方财富概念板块成员每日同步任务

功能:
    1. 通过 AKShare 获取全部东财概念板块列表
    2. 逐板块获取成分股
    3. 批量 upsert 到 stock_concept_map 表

表结构:
    stock_concept_map(stock_code, stock_name, concept_name, updated_at)
    唯一键: (stock_code, concept_name)

用法:
    python -m data_analyst.fetchers.concept_board_fetcher
    python -m data_analyst.fetchers.concept_board_fetcher --limit 20   # 仅同步前20个板块（测试）
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_many

logger = logging.getLogger('myTrader.concept_board_fetcher')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ---------------------------------------------------------------------------
# DDL (run once, alembic migration is the authoritative source)
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_concept_map (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    stock_code  VARCHAR(12) NOT NULL COMMENT '股票代码 (带后缀, e.g. 600519.SH)',
    stock_name  VARCHAR(50) NOT NULL COMMENT '股票名称',
    concept_name VARCHAR(100) NOT NULL COMMENT '东财概念板块名称',
    updated_at  DATETIME NOT NULL COMMENT '最近同步时间',
    UNIQUE KEY uk_stock_concept (stock_code, concept_name),
    INDEX ix_concept_name (concept_name),
    INDEX ix_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财概念板块成员同步表';
"""

# ---------------------------------------------------------------------------
# Board fetcher (sync, run in scheduler or CLI)
# ---------------------------------------------------------------------------

def _normalize_code(code: str) -> Optional[str]:
    """Convert 6-digit code string to exchange-suffixed format."""
    code = str(code).strip().zfill(6)
    # keep only digits
    import re
    code = re.sub(r'[^0-9]', '', code).zfill(6)
    if not code:
        return None
    if code.startswith(('0', '3')):
        return f"{code}.SZ"
    elif code.startswith(('6', '9')):
        return f"{code}.SH"
    elif code.startswith(('4', '8')):
        return f"{code}.BJ"
    return f"{code}.SZ"


def fetch_all_boards() -> list[str]:
    """Return all concept board names from Eastmoney via AKShare."""
    try:
        import akshare as ak
        df = ak.stock_board_concept_name_em()
        boards = df['板块名称'].tolist()
        logger.info('[ConceptFetcher] Total boards: %d', len(boards))
        return boards
    except Exception as e:
        logger.error('[ConceptFetcher] fetch_all_boards failed: %s', e)
        return []


def fetch_board_members(board_name: str) -> list[dict]:
    """Return members of one concept board as [{stock_code, stock_name}]."""
    try:
        import akshare as ak
        df = ak.stock_board_concept_cons_em(symbol=board_name)
        members = []
        for _, row in df.iterrows():
            code = _normalize_code(str(row.get('代码', '')))
            name = str(row.get('名称', '')).strip()
            if code and name:
                members.append({'stock_code': code, 'stock_name': name})
        return members
    except Exception as e:
        logger.warning('[ConceptFetcher] fetch_board_members(%s) failed: %s', board_name, e)
        return []


def upsert_concept_members(rows: list[dict]) -> int:
    """
    Upsert rows into stock_concept_map.
    Each row: {stock_code, stock_name, concept_name, updated_at}
    Returns number of rows affected.
    """
    if not rows:
        return 0
    sql = """
        INSERT INTO stock_concept_map (stock_code, stock_name, concept_name, updated_at)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            stock_name = VALUES(stock_name),
            updated_at = VALUES(updated_at)
    """
    params = [(r['stock_code'], r['stock_name'], r['concept_name'], r['updated_at']) for r in rows]
    execute_many(sql, params, env='online')
    return len(params)


def run_sync(limit: Optional[int] = None, sleep_between: float = 0.5) -> dict:
    """
    Full sync: fetch all boards -> per-board members -> upsert.

    Args:
        limit: Only sync first N boards (for testing).
        sleep_between: Seconds to sleep between board requests (rate limit).

    Returns:
        summary dict with board_count, stock_count, error_count.
    """
    logger.info('[ConceptFetcher] Starting concept board sync...')
    boards = fetch_all_boards()
    if not boards:
        logger.error('[ConceptFetcher] No boards returned, aborting.')
        return {'board_count': 0, 'stock_count': 0, 'error_count': 0}

    if limit:
        boards = boards[:limit]
        logger.info('[ConceptFetcher] Limited to first %d boards.', limit)

    now = datetime.utcnow()
    total_stocks = 0
    error_count = 0
    batch_size = 200  # upsert batch

    for i, board_name in enumerate(boards, 1):
        logger.info('[ConceptFetcher] [%d/%d] Fetching board: %s', i, len(boards), board_name)
        members = fetch_board_members(board_name)
        if not members:
            error_count += 1
            time.sleep(sleep_between)
            continue

        rows = [
            {
                'stock_code': m['stock_code'],
                'stock_name': m['stock_name'],
                'concept_name': board_name,
                'updated_at': now,
            }
            for m in members
        ]

        # upsert in batches
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            try:
                upserted = upsert_concept_members(batch)
                total_stocks += upserted
            except Exception as e:
                logger.error('[ConceptFetcher] upsert failed for board=%s: %s', board_name, e)
                error_count += 1

        time.sleep(sleep_between)

    summary = {
        'board_count': len(boards),
        'stock_count': total_stocks,
        'error_count': error_count,
    }
    logger.info('[ConceptFetcher] Sync done: boards=%d stocks_upserted=%d errors=%d',
                summary['board_count'], summary['stock_count'], summary['error_count'])
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='东财概念板块成员每日同步')
    parser.add_argument('--limit', type=int, default=None, help='Only sync first N boards (testing)')
    parser.add_argument('--sleep', type=float, default=0.5, help='Sleep between board requests (default 0.5s)')
    args = parser.parse_args()

    result = run_sync(limit=args.limit, sleep_between=args.sleep)
    print(f"Done: {result}")
