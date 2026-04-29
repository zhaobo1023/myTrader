# -*- coding: utf-8 -*-
"""
AKShare 数据拉取器

功能：
  1. 使用 AKShare 获取 A 股日线数据（免费、无需 Token）
  2. 支持单只股票和批量拉取
  3. 自动保存到 MySQL

数据来源：东方财富

运行：python data_analyst/fetchers/akshare_fetcher.py
环境：pip install akshare
"""
import sys
import os
import time
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List, Optional, Dict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.db import get_connection, execute_query

# 尝试导入 akshare
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("警告: AKShare 未安装，请运行 pip install akshare")

# ============================================================
# 配置
# ============================================================
TEST_MODE = False
TEST_STOCK = '600519'  # 贵州茅台

NUM_WORKERS = 3  # AKShare 限制并发，不宜太高
DATA_START = '20230101'
REQUEST_DELAY = 0.5  # 请求间隔（秒），避免被限流


# ============================================================
# 数据库辅助
# ============================================================

def get_existing_latest_dates() -> Dict[str, str]:
    """一次性查询所有股票在 DB 中的最新交易日，返回 {stock_code: 'YYYYMMDD'}"""
    rows = execute_query(
        "SELECT stock_code, MAX(trade_date) AS max_date FROM trade_stock_daily GROUP BY stock_code"
    )
    result = {}
    for r in rows:
        if r['max_date']:
            result[r['stock_code']] = r['max_date'].strftime('%Y%m%d')
    return result


def get_all_stock_codes() -> List[str]:
    """获取全部 A 股代码列表（通过 AKShare，东方财富优先，新浪备用）"""
    if not HAS_AKSHARE:
        print("错误: AKShare 未安装")
        return []

    # 方式1: 东方财富实时行情（速度快，字段全）
    try:
        df = ak.stock_zh_a_spot_em()
        codes = df['代码'].tolist()
        print(f"  [东方财富] 获取 {len(codes)} 只股票")
        return codes
    except Exception as e:
        print(f"  [东方财富] 获取失败: {e}, 尝试备用源...")

    # 方式2: 从数据库已有数据获取代码列表
    try:
        rows = execute_query(
            "SELECT DISTINCT stock_code FROM trade_stock_daily"
        )
        if rows:
            codes = []
            for r in rows:
                code = r['stock_code']
                # 去掉 .SH/.SZ 后缀
                if '.' in code:
                    code = code.split('.')[0]
                codes.append(code)
            print(f"  [数据库] 获取 {len(codes)} 只股票")
            return codes
    except Exception as e:
        print(f"  [数据库] 获取失败: {e}")

    return []


# ============================================================
# 核心逻辑
# ============================================================

INSERT_SQL = """
    INSERT INTO trade_stock_daily
    (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount, turnover_rate)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    open_price=VALUES(open_price), high_price=VALUES(high_price),
    low_price=VALUES(low_price), close_price=VALUES(close_price),
    volume=VALUES(volume), amount=VALUES(amount),
    turnover_rate=VALUES(turnover_rate)
"""


def fetch_single_stock(stock_code: str, days: int = 30) -> pd.DataFrame:
    """
    获取单只股票近 N 天的数据

    Args:
        stock_code: 股票代码（如 '600519'）
        days: 天数
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    end_date = date.today().strftime('%Y%m%d')
    start_date = (date.today() - timedelta(days=days + 10)).strftime('%Y%m%d')

    df = ak.stock_zh_a_hist(
        symbol=stock_code,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq"
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # 重命名列
    df = df.rename(columns={
        '日期': 'trade_date',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '成交额': 'amount',
        '换手率': 'turnover_rate'
    })

    return df


def _fetch_hist_eastmoney(stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """东方财富数据源"""
    df = ak.stock_zh_a_hist(
        symbol=stock_code, period="daily",
        start_date=start_date, end_date=end_date, adjust="qfq",
    )
    if df is None or df.empty:
        return None
    return df.rename(columns={
        '日期': 'trade_date', '开盘': 'open', '收盘': 'close',
        '最高': 'high', '最低': 'low', '成交量': 'volume',
        '成交额': 'amount', '换手率': 'turnover_rate',
    })


def _fetch_hist_sina(stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """新浪数据源（备用）"""
    prefix = 'sh' if stock_code.startswith('6') else 'sz'
    df = ak.stock_zh_a_daily(symbol=f"{prefix}{stock_code}", adjust="qfq")
    if df is None or df.empty:
        return None
    df = df.rename(columns={
        'date': 'trade_date', 'open': 'open', 'close': 'close',
        'high': 'high', 'low': 'low', 'volume': 'volume',
        'outstanding_share': '_drop1', 'turnover': 'turnover_rate',
    })
    if 'amount' not in df.columns:
        df['amount'] = None
    # 过滤日期范围
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df['trade_date'] >= start_dt) & (df['trade_date'] <= end_dt)]
    return df if not df.empty else None


# 数据源失败计数，用于动态切换
_eastmoney_failures = 0
_eastmoney_lock = threading.Lock()
_EASTMONEY_FAIL_THRESHOLD = 5


def download_and_save(stock_code: str, start_date: str) -> tuple:
    """增量下载单只股票的日线数据并写入 MySQL（东方财富优先，新浪备用）"""
    global _eastmoney_failures
    if not HAS_AKSHARE:
        return stock_code, 0, "AKShare 未安装"

    try:
        time.sleep(REQUEST_DELAY)  # 限流

        end_date = date.today().strftime('%Y%m%d')
        df = None

        # 东方财富失败过多时直接用新浪
        if _eastmoney_failures < _EASTMONEY_FAIL_THRESHOLD:
            try:
                df = _fetch_hist_eastmoney(stock_code, start_date, end_date)
            except Exception:
                with _eastmoney_lock:
                    _eastmoney_failures += 1
                df = None

        if df is None:
            try:
                df = _fetch_hist_sina(stock_code, start_date, end_date)
            except Exception:
                pass

        if df is None or df.empty:
            return stock_code, 0, None

        # 转换日期格式
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        # 过滤起始日期之后的数据
        start_dt = pd.to_datetime(start_date)
        df = df[df['trade_date'] >= start_dt]

        if df.empty:
            return stock_code, 0, None

        rows = []
        for _, row in df.iterrows():
            trade_date = row['trade_date'].strftime('%Y-%m-%d')
            # 转换股票代码格式： 600519 -> 600519.SH
            full_code = f"{stock_code}.SH" if stock_code.startswith('6') else f"{stock_code}.SZ"
            rows.append((
                full_code, trade_date,
                float(row['open']) if pd.notna(row.get('open')) else None,
                float(row['high']) if pd.notna(row.get('high')) else None,
                float(row['low']) if pd.notna(row.get('low')) else None,
                float(row['close']) if pd.notna(row.get('close')) else None,
                int(row['volume']) if pd.notna(row.get('volume')) else None,
                float(row['amount']) if pd.notna(row.get('amount')) else None,
                float(row['turnover_rate']) if pd.notna(row.get('turnover_rate')) else None,
            ))

        if rows:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany(INSERT_SQL, rows)
                conn.commit()
                cursor.close()
            finally:
                conn.close()

        return stock_code, len(rows), None

    except Exception as e:
        return stock_code, 0, str(e)


def main():
    print("=" * 60)
    print("行情数据采集 (AKShare -> MySQL)")
    if TEST_MODE:
        print("[测试模式] 只采集贵州茅台")
    else:
        print(f"[全量模式] {NUM_WORKERS} 线程并行")
    print("=" * 60)

    if not HAS_AKSHARE:
        print("\n错误: AKShare 未安装，请运行 pip install akshare")
        return

    # 获取股票列表
    if TEST_MODE:
        all_codes = [TEST_STOCK]
        print(f"\n[测试模式] 只采集 {TEST_STOCK}")
    else:
        print(f"\n获取 A 股股票列表...")
        all_codes = get_all_stock_codes()
        print(f"  共 {len(all_codes)} 只股票")

    # 批量查询 DB 中已有的最新日期
    print("查询数据库已有数据...")
    existing = get_existing_latest_dates()
    recent_cutoff = date.today().strftime('%Y%m%d')

    tasks = []
    skip_count = 0
    for code in all_codes:
        latest = existing.get(code) or existing.get(f"{code}.SH") or existing.get(f"{code}.SZ")
        if latest and latest >= recent_cutoff:
            skip_count += 1
            continue
        start = latest if latest else DATA_START
        tasks.append((code, start))

    print(f"  需更新: {len(tasks)} 只, 跳过(今日已有数据): {skip_count} 只")

    if not tasks:
        print("\n全部已是最新，无需更新")
        _print_summary()
        return

    total = len(tasks)
    total_rows = 0
    success_count = 0
    fail_list = []
    start_time = time.time()

    if total <= 5:
        for i, (code, start) in enumerate(tasks, 1):
            print(f"\n[{i}/{total}] {code} (从 {start} 开始)")
            _, count, err = download_and_save(code, start)
            if err is not None:
                print(f"  失败: {err}")
                fail_list.append(code)
            else:
                print(f"  写入 {count} 条")
                success_count += 1
                total_rows += count
    else:
        print(f"\n并行下载（{NUM_WORKERS} 线程)...")

        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {executor.submit(download_and_save, *t): t[0] for t in tasks}
            done = 0
            for future in as_completed(futures):
                code, count, err = future.result()
                done += 1

                if err is not None:
                    fail_list.append(code)
                else:
                    success_count += 1
                    total_rows += count

                elapsed = time.time() - start_time
                speed = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / speed if speed > 0 else 0
                sys.stdout.write(
                    f"\r  进度 {done}/{total} ({done*100/total:.1f}%) | "
                    f"{speed:.1f} 只/秒 | 剩余约 {eta:.0f}秒 | "
                    f"成功 {success_count} 失败 {len(fail_list)}    "
                )
                sys.stdout.flush()

        print()

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"采集完成! 耗时 {elapsed:.1f} 秒")
    print(f"  成功: {success_count}/{total} 只股票")
    print(f"  总写入: {total_rows:,} 条记录")

    if fail_list:
        print(f"  失败 {len(fail_list)} 只: {fail_list[:20]}{'...' if len(fail_list) > 20 else ''}")

    _print_summary()


def _print_summary():
    summary = execute_query("""
        SELECT COUNT(DISTINCT stock_code) as stock_cnt,
               COUNT(*) as row_cnt,
               MIN(trade_date) as min_date, MAX(trade_date) as max_date
        FROM trade_stock_daily
    """)
    if summary:
        row = summary[0]
        print(f"\n数据库 trade_stock_daily 概况:")
        print(f"  {row['stock_cnt']} 只股票, {row['row_cnt']:,} 条记录")
        print(f"  日期范围: {row['min_date']} ~ {row['max_date']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
