# -*- coding: utf-8 -*-
"""
历史每日行情估值数据补充脚本

补充 trade_stock_daily_basic 表的历史数据（2022 至今）。
数据源：AKShare stock_value_em，提供每日 PE_TTM、总市值、流通市值等。

用法：
  # 补充 2022-01-01 起的历史数据（跳过已有数据的股票）
  DB_ENV=online python data_analyst/financial_fetcher/daily_basic_history_fetcher.py

  # 指定日期范围
  DB_ENV=online python data_analyst/financial_fetcher/daily_basic_history_fetcher.py \
    --start 2022-01-01 --end 2024-12-31

  # 强制覆盖已有数据
  DB_ENV=online python data_analyst/financial_fetcher/daily_basic_history_fetcher.py --force

  # 测试模式（只跑 5 只股票）
  DB_ENV=online python data_analyst/financial_fetcher/daily_basic_history_fetcher.py --test
"""
import os
import sys
import time
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from typing import Optional

import pandas as pd
import akshare as ak

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import get_connection

_log_dir = os.path.join(ROOT, 'output', 'microcap')
os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(_log_dir, 'daily_basic_history.log'), mode='a'),
    ]
)
logger = logging.getLogger(__name__)

# 列映射：AKShare -> 数据库字段
COLUMN_MAP = {
    '数据日期': 'trade_date',
    '总市值':   'total_mv',
    '流通市值': 'circ_mv',
    'PE(TTM)': 'pe_ttm',
    '市净率':   'pb',
    '市销率':   'ps_ttm',
    '总股本':   'total_share',
    '流通股本': 'circ_share',
}

SLEEP_PER_REQUEST = 0.3   # 秒，防 API 限流
MAX_WORKERS = 3            # 并发线程数
BATCH_SIZE = 500           # 单次 INSERT 批量大小


def get_stock_list() -> list:
    """从数据库获取全量 A 股股票代码列表。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT stock_code FROM trade_stock_daily
            ORDER BY stock_code
        """)
        codes = [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
    return codes


def get_already_fetched_stocks(start_date: str) -> set:
    """
    查询已有历史数据的股票集合（用于断点续跑跳过）。
    判断依据：该股票在 start_date 之后 90 天内已有数据，说明本次已拉取过。
    """
    from datetime import timedelta
    threshold = (date.fromisoformat(start_date) + timedelta(days=90)).isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT stock_code FROM trade_stock_daily_basic
            WHERE trade_date <= %s
              AND trade_date >= %s
        """, (threshold, start_date))
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def _to_ak_symbol(stock_code: str) -> str:
    """
    将数据库 stock_code（如 000858.SZ / 600519.SH）转为 AKShare 用的纯数字代码。
    """
    return stock_code.split('.')[0]


def fetch_one(stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    拉取单只股票的历史每日估值数据。

    Returns:
        包含 trade_date, total_mv, circ_mv, pe_ttm, pb, ps_ttm,
        total_share, circ_share, stock_code 的 DataFrame，或 None（失败时）
    """
    symbol = _to_ak_symbol(stock_code)
    try:
        raw = ak.stock_value_em(symbol=symbol)
        if raw is None or raw.empty:
            return None

        # 保留需要的列
        raw = raw.rename(columns=COLUMN_MAP)
        keep = list(COLUMN_MAP.values())
        raw = raw[[c for c in keep if c in raw.columns]].copy()

        # 过滤日期范围
        raw['trade_date'] = pd.to_datetime(raw['trade_date']).dt.date
        raw = raw[(raw['trade_date'] >= date.fromisoformat(start_date)) &
                  (raw['trade_date'] <= date.fromisoformat(end_date))]

        if raw.empty:
            return None

        raw['stock_code'] = stock_code

        # AKShare total_mv/circ_mv 单位为元，数据库存 亿元，除以 1e8
        for col in ('total_mv', 'circ_mv'):
            if col in raw.columns:
                raw[col] = raw[col] / 1e8

        # 截断超出 DECIMAL(10,4) 范围的值（极端亏损股 pe_ttm 可能为 ±数百万）
        # pe_ttm/pb/ps_ttm 最大绝对值限为 99999
        for col in ('pe_ttm', 'pb', 'ps_ttm'):
            if col in raw.columns:
                raw[col] = pd.to_numeric(raw[col], errors='coerce')
                raw.loc[raw[col].abs() > 99999, col] = None

        return raw

    except Exception as e:
        logger.warning(f"[WARN] {stock_code} fetch failed: {e}")
        return None


def upsert_batch(rows: list) -> int:
    """批量写入数据库，ON DUPLICATE KEY UPDATE。"""
    if not rows:
        return 0

    conn = get_connection()
    try:
        cursor = conn.cursor()
        sql = """
            INSERT INTO trade_stock_daily_basic
                (stock_code, trade_date, total_mv, circ_mv, pe_ttm, pb, ps_ttm,
                 total_share, circ_share)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_mv    = VALUES(total_mv),
                circ_mv     = VALUES(circ_mv),
                pe_ttm      = VALUES(pe_ttm),
                pb          = VALUES(pb),
                ps_ttm      = VALUES(ps_ttm),
                total_share = VALUES(total_share),
                circ_share  = VALUES(circ_share)
        """
        cursor.executemany(sql, rows)
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def df_to_rows(df: pd.DataFrame) -> list:
    """DataFrame -> SQL 参数 list。"""
    rows = []
    cols = ['stock_code', 'trade_date', 'total_mv', 'circ_mv', 'pe_ttm',
            'pb', 'ps_ttm', 'total_share', 'circ_share']
    for _, row in df.iterrows():
        rows.append(tuple(
            None if pd.isna(row.get(c)) else row.get(c)
            for c in cols
        ))
    return rows


def run(start_date: str, end_date: str, force: bool = False, test: bool = False):
    """主流程。"""
    os.makedirs(os.path.join(ROOT, 'output', 'microcap'), exist_ok=True)

    logger.info("=" * 60)
    logger.info("历史每日行情估值补充脚本")
    logger.info(f"日期范围: {start_date} ~ {end_date}")
    logger.info(f"force={force}, test={test}")
    logger.info("=" * 60)

    # 获取股票列表
    logger.info("[1/3] 获取股票列表...")
    all_codes = get_stock_list()
    logger.info(f"[OK] 共 {len(all_codes)} 只股票")

    if not force:
        already = get_already_fetched_stocks(start_date)
        codes = [c for c in all_codes if c not in already]
        logger.info(f"[OK] 跳过已有历史数据: {len(already)} 只, 待拉取: {len(codes)} 只")
    else:
        codes = all_codes
        logger.info("[OK] force 模式，全量覆盖")

    if test:
        codes = codes[:5]
        logger.info(f"[OK] 测试模式，只拉取前 5 只: {codes}")

    if not codes:
        logger.info("[OK] 无需拉取，数据已是最新")
        return

    logger.info(f"[2/3] 拉取 {len(codes)} 只股票的历史估值数据...")

    success, failed = 0, 0
    pending_rows = []

    def flush(force_flush=False):
        nonlocal pending_rows
        if len(pending_rows) >= BATCH_SIZE or force_flush:
            upsert_batch(pending_rows)
            pending_rows = []

    def fetch_and_collect(stock_code):
        df = fetch_one(stock_code, start_date, end_date)
        time.sleep(SLEEP_PER_REQUEST)
        return stock_code, df

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_and_collect, c): c for c in codes}
        for i, future in enumerate(as_completed(futures), 1):
            stock_code, df = future.result()
            if df is not None and not df.empty:
                pending_rows.extend(df_to_rows(df))
                success += 1
                flush()
            else:
                failed += 1

            if i % 100 == 0 or i == len(codes):
                flush(force_flush=True)
                logger.info(f"  进度: {i}/{len(codes)}, 成功={success}, 失败={failed}")

    flush(force_flush=True)

    logger.info("[3/3] 验证数据库...")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MIN(trade_date), MAX(trade_date),
                   COUNT(DISTINCT trade_date), COUNT(DISTINCT stock_code), COUNT(*)
            FROM trade_stock_daily_basic
        """)
        row = cursor.fetchone()
        logger.info(f"[OK] trade_stock_daily_basic 概况:")
        logger.info(f"     日期范围: {row[0]} ~ {row[1]}")
        logger.info(f"     交易日数: {row[2]}, 股票数: {row[3]}, 总记录: {row[4]}")
    finally:
        conn.close()

    logger.info("=" * 60)
    logger.info(f"[OK] 完成! 成功: {success}, 失败: {failed}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='补充 trade_stock_daily_basic 历史数据')
    parser.add_argument('--start', default='2022-01-01', help='开始日期 (默认 2022-01-01)')
    parser.add_argument('--end',   default=date.today().isoformat(), help='结束日期 (默认今天)')
    parser.add_argument('--force', action='store_true', help='强制覆盖已有数据')
    parser.add_argument('--test',  action='store_true', help='测试模式，只拉 5 只股票')
    args = parser.parse_args()
    run(args.start, args.end, force=args.force, test=args.test)


if __name__ == '__main__':
    main()
