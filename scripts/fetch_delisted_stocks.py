# -*- coding: utf-8 -*-
"""
退市股历史数据补全脚本

功能：
1. 从 AKShare 获取上交所/深交所退市股票列表
2. 筛选出策略回测区间内曾活跃的退市股（2020-01-01 ~ 今日）
3. 尝试逐只拉取历史日线数据，写入 trade_stock_daily 和 trade_stock_daily_basic
4. 对拉取失败的股票记录到 output/microcap/delist_fetch_errors.csv

用法：
    DB_ENV=online python scripts/fetch_delisted_stocks.py
    DB_ENV=online python scripts/fetch_delisted_stocks.py --dry-run   # 仅打印列表，不写库
    DB_ENV=online python scripts/fetch_delisted_stocks.py --start 2022-01-01

注意：
- AKShare 对退市股的历史数据覆盖率不完整，部分股票可能无法拉取
- 建议分批运行，避免触发 API 频率限制
- 深交所接口（stock_info_sz_delist）有时有 SSL 问题，脚本做了降级处理
"""
import os
import sys
import logging
import argparse
import time
from datetime import datetime, date
from typing import List, Dict, Optional

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import get_connection, execute_many

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(ROOT, 'output', 'microcap')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 数据拉取起始日期（覆盖回测区间）
DEFAULT_START = '2020-01-01'


def get_sh_delist_list() -> pd.DataFrame:
    """获取上交所退市股票列表。"""
    try:
        import akshare as ak
        df = ak.stock_info_sh_delist()
        df.columns = ['stock_code', 'name', 'list_date', 'delist_date']
        df['exchange'] = 'SH'
        logger.info(f"[OK] 上交所退市股: {len(df)} 只")
        return df
    except Exception as e:
        logger.error(f"[ERROR] 上交所退市股拉取失败: {e}")
        return pd.DataFrame()


def get_sz_delist_list() -> pd.DataFrame:
    """获取深交所退市股票列表（SSL 问题时降级为空）。"""
    try:
        import akshare as ak
        df = ak.stock_info_sz_delist()
        # 深交所返回列名可能不同，做兼容处理
        if '证券代码' in df.columns:
            df = df.rename(columns={
                '证券代码': 'stock_code',
                '证券简称': 'name',
                '上市日期': 'list_date',
                '终止上市日期': 'delist_date',
            })
        df['exchange'] = 'SZ'
        logger.info(f"[OK] 深交所退市股: {len(df)} 只")
        return df
    except Exception as e:
        logger.warning(f"[WARN] 深交所退市股拉取失败（SSL问题常见）: {e}")
        return pd.DataFrame()


def standardize_code(code: str, exchange: str) -> str:
    """将纯数字代码转为 xxxxxx.SH/SZ 格式。"""
    code = str(code).strip().zfill(6)
    if '.' in code:
        return code
    return f"{code}.{exchange}"


def fetch_daily_data(stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    从 AKShare 拉取退市股历史日线数据。

    Args:
        stock_code: 格式 '600001.SH' 或 '000001.SZ'
        start_date: 'YYYY-MM-DD'
        end_date:   'YYYY-MM-DD'

    Returns:
        DataFrame 或 None（失败时）
    """
    try:
        import akshare as ak
        # AKShare 接受纯数字代码
        pure_code = stock_code.split('.')[0]
        start_compact = start_date.replace('-', '')
        end_compact   = end_date.replace('-', '')

        df = ak.stock_zh_a_hist(
            symbol=pure_code,
            period='daily',
            start_date=start_compact,
            end_date=end_compact,
            adjust='',     # 不复权（与现有数据保持一致）
        )
        if df is None or df.empty:
            return None

        df = df.rename(columns={
            '日期': 'trade_date',
            '开盘': 'open_price',
            '最高': 'high_price',
            '最低': 'low_price',
            '收盘': 'close_price',
            '成交量': 'volume',
            '成交额': 'amount',
            '换手率': 'turnover_rate',
        })
        df['stock_code'] = stock_code
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
        return df
    except Exception as e:
        logger.debug(f"  拉取 {stock_code} 失败: {e}")
        return None


def check_existing_dates(stock_code: str, env: str = 'online') -> set:
    """查询数据库中已有该股票的交易日期集合，避免重复写入。"""
    conn = get_connection(env=env)
    try:
        df = pd.read_sql(
            "SELECT trade_date FROM trade_stock_daily WHERE stock_code = %s",
            conn, params=[stock_code]
        )
        return set(df['trade_date'].astype(str))
    except Exception:
        return set()
    finally:
        conn.close()


def write_daily_data(df: pd.DataFrame, env: str = 'online') -> int:
    """将日线数据写入 trade_stock_daily，返回写入行数。"""
    required_cols = ['stock_code', 'trade_date', 'open_price', 'high_price',
                     'low_price', 'close_price', 'volume', 'amount']
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    rows = [
        (row['stock_code'], row['trade_date'], row.get('open_price'),
         row.get('high_price'), row.get('low_price'), row.get('close_price'),
         row.get('volume'), row.get('amount'), row.get('turnover_rate'))
        for _, row in df.iterrows()
    ]

    sql = """
        INSERT IGNORE INTO trade_stock_daily
        (stock_code, trade_date, open_price, high_price, low_price,
         close_price, volume, amount, turnover_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        execute_many(sql, rows, env=env)
        return len(rows)
    except Exception as e:
        logger.error(f"  写入 trade_stock_daily 失败: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description='退市股历史数据补全')
    parser.add_argument('--start',   default=DEFAULT_START, help='数据起始日期')
    parser.add_argument('--end',     default=date.today().strftime('%Y-%m-%d'), help='数据结束日期')
    parser.add_argument('--dry-run', action='store_true', help='仅打印，不写库')
    parser.add_argument('--limit',   type=int, default=0, help='最多处理 N 只（0=全部），用于测试')
    parser.add_argument('--sleep',   type=float, default=0.5, help='每只股票拉取间隔（秒）')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("退市股历史数据补全")
    logger.info(f"数据范围: {args.start} ~ {args.end}")
    logger.info(f"dry_run={args.dry_run}, limit={args.limit or '无限制'}")
    logger.info("=" * 60)

    # 获取退市股列表
    sh_df = get_sh_delist_list()
    sz_df = get_sz_delist_list()
    all_delist = pd.concat([sh_df, sz_df], ignore_index=True)

    if all_delist.empty:
        logger.error("[ERROR] 未能获取任何退市股列表，退出")
        sys.exit(1)

    # 标准化股票代码
    all_delist['stock_code'] = all_delist.apply(
        lambda r: standardize_code(r['stock_code'], r['exchange']), axis=1
    )

    # 过滤：保留在数据范围内有活跃记录的退市股
    # delist_date >= args.start 表示在我们关心的区间内还活跃过
    all_delist['delist_date'] = pd.to_datetime(
        all_delist['delist_date'], errors='coerce'
    ).dt.strftime('%Y-%m-%d')
    active_in_range = all_delist[
        all_delist['delist_date'].notna() &
        (all_delist['delist_date'] >= args.start)
    ].copy()

    logger.info(f"退市股总计: {len(all_delist)} 只，{args.start} 之后退市: {len(active_in_range)} 只")

    if args.limit > 0:
        active_in_range = active_in_range.head(args.limit)
        logger.info(f"限制处理前 {args.limit} 只")

    if args.dry_run:
        logger.info("[DRY-RUN] 退市股列表（前 20 只）:")
        for _, row in active_in_range.head(20).iterrows():
            logger.info(f"  {row['stock_code']}  {row.get('name', '')}  退市日: {row['delist_date']}")
        return

    # 逐只拉取
    results = []
    for idx, row in active_in_range.iterrows():
        code = row['stock_code']
        delist_date = row['delist_date']
        fetch_end = min(delist_date, args.end)   # 只拉到退市日

        logger.info(f"[{len(results)+1}/{len(active_in_range)}] 拉取 {code} ({row.get('name', '')})"
                    f"  {args.start} ~ {fetch_end}")

        # 检查已有数据
        existing_dates = check_existing_dates(code)

        df = fetch_daily_data(code, args.start, fetch_end)
        time.sleep(args.sleep)

        if df is None or df.empty:
            results.append({'stock_code': code, 'status': 'no_data', 'rows_written': 0})
            logger.warning(f"  [WARN] {code}: 无数据")
            continue

        # 过滤已有日期
        df = df[~df['trade_date'].isin(existing_dates)]
        if df.empty:
            results.append({'stock_code': code, 'status': 'already_exists', 'rows_written': 0})
            logger.info(f"  [SKIP] {code}: 数据已存在")
            continue

        written = write_daily_data(df)
        results.append({'stock_code': code, 'status': 'ok', 'rows_written': written})
        logger.info(f"  [OK] {code}: 写入 {written} 行")

    # 保存结果报告
    results_df = pd.DataFrame(results)
    report_file = os.path.join(OUTPUT_DIR, 'delist_fetch_report.csv')
    results_df.to_csv(report_file, index=False)

    ok_count    = int((results_df['status'] == 'ok').sum())
    skip_count  = int((results_df['status'] == 'already_exists').sum())
    fail_count  = int((results_df['status'] == 'no_data').sum())
    total_rows  = int(results_df['rows_written'].sum())

    logger.info("=" * 60)
    logger.info(f"完成: 成功={ok_count}, 已存在={skip_count}, 无数据={fail_count}")
    logger.info(f"共写入 {total_rows} 行")
    logger.info(f"报告: {report_file}")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
