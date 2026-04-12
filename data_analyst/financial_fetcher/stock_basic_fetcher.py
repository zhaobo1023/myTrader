# -*- coding: utf-8 -*-
"""
全A股票基本信息拉取脚本

从 AKShare 获取全量 A 股列表（股票代码、名称、ST 状态）并写入 trade_stock_basic 表。
支持 --sync-from-local 模式，从本地数据库同步到线上。

用法：
  # 从 AKShare 拉取并写入 DB_ENV 指定的数据库
  DB_ENV=online python -m data_analyst.financial_fetcher.stock_basic_fetcher

  # 从本地数据库同步到线上（推荐，无需外网）
  python -m data_analyst.financial_fetcher.stock_basic_fetcher --sync-from-local --env online
"""
import os
import sys
import logging
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import get_connection, execute_query

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(ROOT, 'output', 'microcap', 'stock_basic_fetch.log'),
            mode='a',
        ),
    ]
)
logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO trade_stock_basic (stock_code, stock_name, is_st)
VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE
    stock_name = VALUES(stock_name),
    is_st = VALUES(is_st)
"""


def convert_code(code: str) -> str:
    """6 位纯数字 -> xxxx.SH / xxxx.SZ"""
    code = str(code).strip()
    if code.startswith('6'):
        return f"{code}.SH"
    return f"{code}.SZ"


def detect_st(name: str) -> int:
    """从名称判断 ST 状态"""
    return 1 if 'ST' in name.upper() else 0


def write_rows(rows: list, env: str) -> None:
    """批量写入数据库"""
    st_count = sum(1 for r in rows if r[2] == 1)
    logger.info("Total stocks: %d, ST stocks: %d, Normal: %d",
                len(rows), st_count, len(rows) - st_count)

    conn = get_connection(env)
    try:
        cursor = conn.cursor()
        cursor.executemany(UPSERT_SQL, rows)
        conn.commit()
        logger.info("Written %d rows to trade_stock_basic (env=%s)", cursor.rowcount, env)
        cursor.close()
    finally:
        conn.close()


def fetch_from_akshare_and_write(env: str) -> None:
    """从 AKShare 拉取全量 A 股并写入数据库"""
    import akshare as ak

    logger.info("Fetching stock list from AKShare ...")
    df = ak.stock_zh_a_spot_em()

    if df is None or df.empty:
        logger.error("AKShare returned empty data")
        return

    rows = []
    for _, r in df.iterrows():
        code = convert_code(str(r['代码']))
        name = str(r['名称']).strip()
        is_st = detect_st(name)
        rows.append((code, name, is_st))

    write_rows(rows, env)


def sync_from_local(target_env: str) -> None:
    """从本地 trade_stock_basic 同步到目标环境"""
    logger.info("Reading stock_basic from local database ...")
    records = execute_query(
        "SELECT stock_code, stock_name, is_st FROM trade_stock_basic", env='local'
    )
    if not records:
        logger.error("Local trade_stock_basic is empty, nothing to sync")
        return

    rows = [(r['stock_code'], r['stock_name'], int(r['is_st'])) for r in records]
    write_rows(rows, target_env)


def main():
    parser = argparse.ArgumentParser(description='Fetch stock basic info')
    parser.add_argument('--env', default=None, choices=['local', 'online'],
                        help='Target database env (default: DB_ENV)')
    parser.add_argument('--sync-from-local', action='store_true',
                        help='Sync from local DB instead of fetching from AKShare')
    args = parser.parse_args()

    env = args.env or os.getenv('DB_ENV', 'local')
    logger.info("Target env: %s", env)

    if args.sync_from_local:
        sync_from_local(env)
    else:
        fetch_from_akshare_and_write(env)


if __name__ == '__main__':
    main()
