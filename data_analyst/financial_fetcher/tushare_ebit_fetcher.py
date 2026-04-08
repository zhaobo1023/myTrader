# -*- coding: utf-8 -*-
"""
EBIT/EBITDA 数据拉取器

功能：
  1. 从 AKShare stock_profit_sheet_by_report_em API 拉取 EBIT/EBITDA 数据
  2. 覆盖过去 5 年年报（2020-2026 年报，report_date = XXXX-12-31）
  3. 建表 trade_stock_ebit (online 环境)
  4. 批量入库，频率控制 (0.5s/次，3 并发)
  5. 支持增量更新和全量重跑

运行：
  python data_analyst/financial_fetcher/tushare_ebit_fetcher.py
  python data_analyst/financial_fetcher/tushare_ebit_fetcher.py --test
  python data_analyst/financial_fetcher/tushare_ebit_fetcher.py --start-date 2024-12-31 --end-date 2025-12-31

环境：使用 online 数据库，无需 TUSHARE_TOKEN
"""
import sys
import os
import time
import logging
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Tuple
from decimal import Decimal

import pandas as pd
import akshare as ak

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import get_connection, execute_query, execute_many

# 日志配置
log_dir = os.path.join(ROOT, 'output', 'microcap')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'ebit_fetch.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================
NUM_WORKERS = 3  # 并发线程数
REQUEST_DELAY = 0.5  # 请求间隔（秒）
TEST_MODE = False
TEST_STOCK = '000858'  # 五粮液
DEFAULT_START_DATE = '2020-12-31'  # 2020 年报
DEFAULT_END_DATE = '2026-12-31'  # 2026 年报

def _to_em_symbol(stock_code: str) -> str:
    """转换为东方财富格式: 600519 -> sh600519"""
    code = stock_code.strip()
    if code.startswith(("sh", "sz", "SH", "SZ")):
        return code.lower()
    prefix = "sh" if code.startswith("6") else "sz"
    return prefix + code


def create_table():
    """创建 trade_stock_ebit 表（online 环境）"""
    sql = """
    CREATE TABLE IF NOT EXISTS trade_stock_ebit (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        stock_code VARCHAR(20) NOT NULL,
        report_date DATE NOT NULL COMMENT '报告期（年报/中报/季报）',
        ebit DECIMAL(20,2) COMMENT '息税前利润(元)',
        ebitda DECIMAL(20,2) COMMENT 'EBITDA(元)',
        total_revenue DECIMAL(20,2) COMMENT '营业总收入(元)',
        interest_expense DECIMAL(20,2) COMMENT '财务费用(元)',
        income_tax DECIMAL(20,2) COMMENT '所得税费用(元)',
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_stock_report (stock_code, report_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='EBIT数据（来自Tushare）'
    """
    try:
        conn = get_connection(env='online')
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("[OK] 表 trade_stock_ebit 已创建或已存在")
    except Exception as e:
        logger.error(f"[ERROR] 创建表失败: {e}")
        raise


def get_all_stock_codes() -> List[str]:
    """获取全部 A 股代码列表（通过 Tushare）"""
    if not HAS_TUSHARE:
        logger.error("[ERROR] Tushare 未安装")
        return []

    try:
        pro = get_pro()
        # 获取沪深A股列表（不含B股）
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code')
        codes = []
        for ts_code in df['ts_code'].tolist():
            # 转换格式: 600519.SH -> 600519
            code = ts_code.split('.')[0]
            codes.append(code)
        logger.info(f"[OK] 获取 A 股代码 {len(codes)} 只")
        return codes
    except Exception as e:
        logger.error(f"[ERROR] 获取股票列表失败: {e}")
        return []


def get_existing_report_dates() -> Dict[str, set]:
    """查询数据库中已有的 (stock_code, report_date) 组合"""
    rows = execute_query(
        "SELECT stock_code, report_date FROM trade_stock_ebit",
        env='online'
    )
    result = {}
    for row in rows:
        code = row['stock_code']
        date = row['report_date']
        if code not in result:
            result[code] = set()
        result[code].add(date)
    return result


def safe_decimal(val) -> Optional[Decimal]:
    """安全转换为 Decimal"""
    try:
        if pd.isna(val) or val is None:
            return None
        val_str = str(val).strip()
        if val_str in ('--', '-', '', 'nan', 'NaN'):
            return None
        return Decimal(str(float(val_str)))
    except Exception:
        return None


def fetch_ebit_data(stock_code: str, start_date: str, end_date: str) -> Tuple[str, List[dict]]:
    """
    拉取单只股票的 EBIT 数据

    Args:
        stock_code: 股票代码（6位，如 000858）
        start_date: 开始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）

    Returns:
        (stock_code, 数据列表)
    """
    records = []

    try:
        time.sleep(REQUEST_DELAY)

        # 转换为东方财富格式: 000858 -> sz000858
        em_symbol = _to_em_symbol(stock_code)

        # 调用 akshare API 拉取利润表
        df = ak.stock_profit_sheet_by_report_em(symbol=em_symbol)

        if df is None or df.empty:
            logger.debug(f"[WARN] {stock_code} 无利润表数据")
            return stock_code, records

        # 解析数据
        for _, row in df.iterrows():
            try:
                report_date_str = str(row.get('REPORT_DATE', '')).strip()
                if not report_date_str or len(report_date_str) < 10:
                    continue

                report_date = datetime.strptime(report_date_str[:10], '%Y-%m-%d').date()

                # 过滤日期范围
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                if not (start_dt <= report_date <= end_dt):
                    continue

                record = {
                    'stock_code': stock_code,
                    'report_date': report_date,
                    'ebit': safe_decimal(row.get('OPERATE_PROFIT')),
                    'ebitda': None,
                    'total_revenue': safe_decimal(row.get('TOTAL_OPERATE_INCOME')),
                    'interest_expense': safe_decimal(row.get('FINANCE_EXPENSE')),
                    'income_tax': safe_decimal(row.get('INCOME_TAX')),
                }
                records.append(record)
            except Exception as e:
                logger.debug(f"[WARN] {stock_code} 解析行数据失败: {e}")
                continue

        if records:
            logger.info(f"[OK] {stock_code} 拉取 EBIT {len(records)} 条")
        return stock_code, records

    except Exception as e:
        logger.error(f"[ERROR] {stock_code} 拉取 EBIT 失败: {e}")
        return stock_code, []


def save_ebit_data(records: List[dict]) -> int:
    """
    将 EBIT 数据批量保存到数据库

    Args:
        records: 数据列表

    Returns:
        插入行数
    """
    if not records:
        return 0

    # 转换为 tuple 列表供 executemany 使用
    data_tuples = []
    for r in records:
        data_tuples.append((
            r['stock_code'],
            r['report_date'],
            r['ebit'],
            r['ebitda'],
            r['total_revenue'],
            r['interest_expense'],
            r['income_tax'],
        ))

    insert_sql = """
    INSERT INTO trade_stock_ebit
    (stock_code, report_date, ebit, ebitda, total_revenue, interest_expense, income_tax)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    ebit=VALUES(ebit), ebitda=VALUES(ebitda),
    total_revenue=VALUES(total_revenue), interest_expense=VALUES(interest_expense),
    income_tax=VALUES(income_tax)
    """

    try:
        affected = execute_many(insert_sql, data_tuples, env='online')
        logger.info(f"[OK] 写入/更新 {affected} 条记录")
        return affected
    except Exception as e:
        logger.error(f"[ERROR] 数据保存失败: {e}")
        return 0


def main(test_mode: bool = False, start_date: str = DEFAULT_START_DATE, end_date: str = DEFAULT_END_DATE):
    """主函数"""
    logger.info("=" * 60)
    logger.info("EBIT 数据拉取器 (来自 AKShare)")
    logger.info(f"环境: online")
    logger.info(f"日期范围: {start_date} 到 {end_date}")

    if test_mode:
        logger.info(f"[测试模式] 只拉取 {TEST_STOCK}")
    else:
        logger.info(f"[全量模式] {NUM_WORKERS} 线程并行")
    logger.info("=" * 60)

    # 创建表
    logger.info("\n[1/3] 创建表...")
    create_table()

    # 获取股票列表
    logger.info("\n[2/3] 获取股票列表...")
    if test_mode:
        all_codes = [TEST_STOCK]
        logger.info(f"[测试模式] 只拉取 {TEST_STOCK}")
    else:
        all_codes = get_all_stock_codes()
        if not all_codes:
            logger.error("[ERROR] 无法获取股票列表")
            return
        logger.info(f"[OK] 共 {len(all_codes)} 只股票")

    # 获取已有数据
    logger.info("\n[3/3] 拉取 EBIT 数据...")
    existing = get_existing_report_dates()

    # 准备任务
    tasks = []
    skip_count = 0
    for code in all_codes:
        # 跳过已有完整数据的股票（简化处理：只判断是否有任何数据）
        if code in existing and len(existing[code]) > 0:
            skip_count += 1
            continue
        tasks.append((code, start_date, end_date))

    logger.info(f"需拉取: {len(tasks)} 只, 跳过(已有数据): {skip_count} 只")

    if not tasks:
        logger.info("[OK] 全部已是最新，无需更新")
        _print_summary()
        return

    # 执行拉取
    total = len(tasks)
    total_records = 0
    success_count = 0
    fail_list = []
    start_time = time.time()
    all_fetched_records = []

    if total <= 5:
        # 串行执行（调试用）
        logger.info(f"\n串行执行 {total} 只股票...")
        for i, (code, start, end) in enumerate(tasks, 1):
            logger.info(f"[{i}/{total}] {code}")
            _, records = fetch_ebit_data(code, start, end)
            if records:
                success_count += 1
                total_records += len(records)
                all_fetched_records.extend(records)
            else:
                fail_list.append(code)
    else:
        # 并行执行
        logger.info(f"\n并行下载（{NUM_WORKERS} 线程)...")
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {executor.submit(fetch_ebit_data, code, start, end): code
                       for code, start, end in tasks}
            done = 0
            for future in as_completed(futures):
                code, records = future.result()
                done += 1
                if records:
                    success_count += 1
                    total_records += len(records)
                    all_fetched_records.extend(records)
                else:
                    fail_list.append(code)

                elapsed = time.time() - start_time
                speed = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / speed if speed > 0 else 0
                pct = done * 100 / total
                sys.stdout.write(
                    f"\r  进度 {done}/{total} ({pct:.1f}%) | "
                    f"{speed:.1f} 只/秒 | 剩余约 {eta:.0f}秒 | "
                    f"成功 {success_count} 失败 {len(fail_list):,}    "
                )
                sys.stdout.flush()
        print()

    # 批量保存
    logger.info(f"\n保存数据到数据库...")
    if all_fetched_records:
        saved = save_ebit_data(all_fetched_records)
        logger.info(f"[OK] 保存 {saved} 条记录")

    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 60)
    logger.info(f"拉取完成! 耗时 {elapsed:.1f} 秒")
    logger.info(f"  成功: {success_count}/{total} 只股票")
    logger.info(f"  总拉取: {total_records:,} 条记录")
    if fail_list:
        logger.info(f"  失败: {len(fail_list):,} 只")
        if len(fail_list) <= 20:
            logger.info(f"        {fail_list}")

    _print_summary()


def _print_summary():
    """打印数据库概况"""
    try:
        summary = execute_query(
            """
            SELECT COUNT(DISTINCT stock_code) as stock_cnt,
                   COUNT(*) as row_cnt,
                   MIN(report_date) as min_date,
                   MAX(report_date) as max_date
            FROM trade_stock_ebit
            """,
            env='online'
        )
        if summary:
            row = summary[0]
            logger.info(f"\n数据库 trade_stock_ebit 概况:")
            logger.info(f"  {row['stock_cnt']} 只股票, {row['row_cnt']:,} 条记录")
            logger.info(f"  日期范围: {row['min_date']} ~ {row['max_date']}")
    except Exception as e:
        logger.error(f"[ERROR] 查询概况失败: {e}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Tushare EBIT 数据拉取器')
    parser.add_argument('--test', action='store_true', help='测试模式（只拉取 000858）')
    parser.add_argument('--start-date', type=str, default=DEFAULT_START_DATE, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=DEFAULT_END_DATE, help='结束日期 (YYYY-MM-DD)')

    args = parser.parse_args()
    main(test_mode=args.test, start_date=args.start_date, end_date=args.end_date)
