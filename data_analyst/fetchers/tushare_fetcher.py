# -*- coding: utf-8 -*-
"""
Tushare 数据拉取器

功能：
  1. 使用 Tushare Pro API 获取 A 股日线数据
  2. 支持单只股票和批量拉取
  3. 自动保存到 MySQL

运行：python data_analyst/fetchers/tushare_fetcher.py
环境：需要设置 TUSHARE_TOKEN 环境变量
"""
import sys
import os
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.db import get_connection, execute_query
from config.settings import TUSHARE_TOKEN

# 尝试导入 tushare
try:
    import tushare as ts
    HAS_TUSHARE = True
except ImportError:
    HAS_TUSHARE = False
    print("警告: Tushare 未安装，请运行 pip install tushare")

if not TUSHARE_TOKEN:
    print("警告: TUSHARE_TOKEN 未配置， Tushare 功能将不可用")


# ============================================================
# 配置
# ============================================================
TEST_MODE = False
TEST_STOCK = '600519.SH'

NUM_WORKERS = 3  # Tushare API 限制并发
DATA_START = '20230101'
REQUEST_DELAY = 0.3  # 请求间隔（秒），避免被限流


# ============================================================
# Tushare API
# ============================================================

_pro = None


def get_pro():
    """获取 Tushare Pro 实例"""
    global _pro
    if _pro is not None:
        return _pro

    token = TUSHARE_TOKEN
    if not token:
        raise RuntimeError("未配置 TUSHARE_TOKEN")
    ts.set_token(token)
    _pro = ts.pro_api()
    return _pro


def get_all_stock_codes() -> List[str]:
    """获取全部 A 股代码列表（通过 Tushare）"""
    if not HAS_TUSHARE:
        print("错误: Tushare 未安装")
        return []

    try:
        pro = get_pro()
        # 获取沪深A股列表
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code')
        return df['ts_code'].tolist()
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return []


def get_existing_latest_dates() -> Dict[str, str]:
    """查询所有股票在 DB 中的最新交易日"""
    rows = execute_query(
        "SELECT stock_code, MAX(trade_date) AS max_date FROM trade_stock_daily GROUP BY stock_code"
    )
    result = {}
    for r in rows:
        if r['max_date']:
            result[r['stock_code']] = r['max_date'].strftime('%Y%m%d')
    return result


# ============================================================
# 数据拉取和保存
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


def fetch_and_save(stock_code: str, start_date: str) -> tuple:
    """拉取单只股票数据并保存"""
    if not HAS_TUSHARE:
        return stock_code, 0, "Tushare 未安装"

    try:
        get_pro()  # 必须调用：内部 ts.set_token() 是副作用，pro 对象本身不用
        time.sleep(REQUEST_DELAY)
        # 获取日线数据
        df = ts.pro_bar(
            ts_code=stock_code,
            start_date=start_date,
            end_date=date.today().strftime('%Y%m%d'),
            adj='qfq',
        )

        if df is None or df.empty:
            return stock_code, 0, "无数据"
        # 夌理数据
        records = []
        for _, row in df.iterrows():
            trade_date = pd.to_datetime(row['trade_date']).strftime('%Y-%m-%d')
            # 转换股票代码格式: 600519.SH -> 600519
            full_code = row['ts_code']
            if not full_code.endswith('.SH') and not full_code.endswith('.SZ'):
                full_code = f"{full_code}.SH" if full_code.startswith('6') else f"{full_code}.SZ"
            records.append((
                full_code, trade_date,
                float(row['open']) if row['open'] else None,
                float(row['high']) if row['high'] else None,
                float(row['low']) if row['low'] else None,
                float(row['close']) if row['close'] else None,
                float(row['vol']) if row['vol'] else None,
                float(row['amount']) if row['amount'] else None,
                float(row.get('turnover_rate')) if pd.notna(row.get('turnover_rate')) else None,
            ))
        # 保存到数据库
        if records:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.executemany(INSERT_SQL, records)
            conn.commit()
            cursor.close()
            conn.close()
        return stock_code, len(records)
    except Exception as e:
        return stock_code, 0, str(e)


def main():
    """主函数 - 批量拉取 A 股日线数据"""
    print("=" * 60)
    print("行情数据采集 (Tushare -> MySQL)")
    if TEST_MODE:
        print("[测试模式] 只采集贵州茅台")
    else:
        print(f"[全量模式] {NUM_WORKERS} 线程并行")
    print("=" * 60)

    if not HAS_TUSHARE or not TUSHARE_TOKEN:
        print("\n错误: Tushare 未安装或 TUSHARE_TOKEN 未配置")
        return
    # 获取股票列表
    if TEST_MODE:
        all_codes = [TEST_STOCK]
        print(f"\n[测试模式] 只采集 {TEST_STOCK}")
    else:
        print("\n获取 A 股股票列表...")
        all_codes = get_all_stock_codes()
        print(f"  共 {len(all_codes)} 只股票")
    # 获取已有数据的最新日期
    print("查询数据库已有数据...")
    existing = get_existing_latest_dates()
    today = date.today().strftime('%Y%m%d')
    # 准备任务
    tasks = []
    skip_count = 0
    for code in all_codes:
        latest = existing.get(code)
        if latest and latest >= today:
            skip_count += 1
            continue
        start = latest if latest else DATA_START
        tasks.append((code, start))
    print(f"  需更新: {len(tasks)} 只, 跳过(今日已有数据): {skip_count} 只")
    if not tasks:
        print("\n全部已是最新，无需更新")
        _print_summary()
        return
    # 执行拉取
    total = len(tasks)
    total_rows = 0
    success_count = 0
    fail_list = []
    start_time = time.time()
    if total <= 5:
        # 串行执行
        for i, (code, start) in enumerate(tasks, 1):
            print(f"\n[{i}/{total}] {code} (从 {start} 开始)")
            _, count = fetch_and_save(code, start)
            if count > 0:
                print(f"  写入 {count} 条")
                success_count += 1
                total_rows += count
            else:
                print(f"  {'无数据' if count == 0 else '失败'}")
                if count == 0:
                    fail_list.append(code)
    else:
        # 并行执行
        print(f"\n并行下载（ {NUM_WORKERS} 线程)...")
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {executor.submit(fetch_and_save, code, start): code for code, start in tasks}
            done = 0
            for future in as_completed(futures):
                code, count = future.result()
                done += 1
                if count > 0:
                    success_count += 1
                    total_rows += count
                else:
                    fail_list.append(code)
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
    """打印数据库概况"""
    summary = execute_query("""
        SELECT COUNT(DISTINCT stock_code) as stock_cnt,
               COUNT(*) as row_cnt,
               MIN(trade_date) as min_date, MAX(trade_date) as max_date
        FROM trade_stock_daily
    """)
    if summary:
        row = summary[0]
        print("\n数据库 trade_stock_daily 概况:")
        print(f"  {row['stock_cnt']} 只股票, {row['row_cnt']:,} 条记录")
        print(f"  日期范围: {row['min_date']} ~ {row['max_date']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
