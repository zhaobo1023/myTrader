# -*- coding: utf-8 -*-
"""
估值因子计算模块

估值因子:
- pe_ttm: 市盈率TTM (直接使用)
- pb: 市净率 (直接使用)
- ps_ttm: 市销率TTM (直接使用)
- market_cap: 总市值 (从 total_mv 转换为亿元)
- circ_market_cap: 流通市值 (从 circ_mv 转换为亿元)

运行:
  # 计算今天的因子
  python data_analyst/factors/valuation_factor_calculator.py

  # 回填历史数据
  python data_analyst/factors/valuation_factor_calculator.py --backfill --start 2024-01-01
"""
import sys
import os
import gc
import pandas as pd
import numpy as np
from datetime import date, timedelta
from time import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, get_connection, get_dual_connections, dual_executemany

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 配置
BATCH_SIZE = 500  # 每批处理的股票数量
START_DATE = date.today().strftime('%Y-%m-%d')  # 默认只算今天
END_DATE = date.today().strftime('%Y-%m-%d')
# 估值因子需要日线+基本面数据, 180自然日足够覆盖滚动窗口
DATA_START_DATE = (date.today() - timedelta(days=180)).strftime('%Y-%m-%d')


def get_all_stock_codes():
    """获取所有股票代码"""
    sql = "SELECT DISTINCT stock_code FROM trade_stock_daily ORDER BY stock_code"
    rows = execute_query(sql)
    return [r['stock_code'] for r in rows]


def load_stock_daily_data(stock_codes, start_date, end_date):
    """批量加载指定股票的K线数据"""
    if not stock_codes:
        return {}

    placeholders = ', '.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, trade_date, open_price, high_price, low_price,
               close_price, volume, amount, turnover_rate
        FROM trade_stock_daily
        WHERE stock_code IN ({placeholders})
          AND trade_date >= %s AND trade_date <= %s
        ORDER BY stock_code, trade_date ASC
    """
    params = stock_codes + [start_date, end_date]
    rows = execute_query(sql, params)

    if not rows:
        return {}

    df_all = pd.DataFrame(rows)
    df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])

    for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'amount', 'turnover_rate']:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce')

    result = {}
    for code in stock_codes:
        group = df_all[df_all['stock_code'] == code]
        if len(group) > 0:
            sub = group.set_index('trade_date').sort_index()
            result[code] = sub

    return result


def load_daily_basic_data(stock_codes, start_date, end_date):
    """
    加载每日基本面数据 (估值数据)

    从 trade_stock_daily_basic 表加载:
    - pe_ttm: 市盈率TTM
    - pb: 市净率
    - ps_ttm: 市销率TTM
    - total_mv: 总市值 (万元)
    - circ_mv: 流通市值 (万元)
    """
    if not stock_codes:
        return {}

    placeholders = ', '.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, trade_date, pe_ttm, pb, ps_ttm, total_mv, circ_mv
        FROM trade_stock_daily_basic
        WHERE stock_code IN ({placeholders})
          AND trade_date >= %s AND trade_date <= %s
        ORDER BY stock_code, trade_date ASC
    """
    params = stock_codes + [start_date, end_date]
    rows = execute_query(sql, params)

    if not rows:
        return {}

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])

    # 转换数值
    for col in ['pe_ttm', 'pb', 'ps_ttm', 'total_mv', 'circ_mv']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    result = {}
    for code in stock_codes:
        group = df[df['stock_code'] == code]
        if len(group) > 0:
            sub = group.set_index('trade_date').sort_index()
            result[code] = sub

    return result


def calc_valuation_factors(daily_df, basic_df):
    """
    计算估值因子

    使用 asof merge 将 daily_basic 数据映射到每个交易日

    Args:
        daily_df: 日线数据 (用于获取交易日历)
        basic_df: 每日基本面数据 (估值数据)

    Returns:
        DataFrame: 估值因子
    """
    if basic_df is None or len(basic_df) == 0:
        return None

    result = pd.DataFrame(index=daily_df.index)

    # 重置索引以便合并
    basic = basic_df.reset_index()
    basic = basic.rename(columns={'trade_date': 'basic_date'})

    # 创建交易日历
    daily_dates = daily_df.index.to_frame(index=False)
    daily_dates['trade_date'] = pd.to_datetime(daily_dates['trade_date'])

    # 使用 asof 合并 (向前查找最近的基本面数据)
    daily_dates_sorted = daily_dates.sort_values('trade_date')
    basic_sorted = basic.sort_values('basic_date')

    merged = pd.merge_asof(
        daily_dates_sorted,
        basic_sorted,
        left_on='trade_date',
        right_on='basic_date',
        direction='backward'  # 向前查找
    )
    merged = merged.set_index('trade_date')

    # 1. pe_ttm - 市盈率TTM (直接使用)
    result['pe_ttm'] = merged['pe_ttm']

    # 2. pb - 市净率 (直接使用)
    result['pb'] = merged['pb']

    # 3. ps_ttm - 市销率TTM (直接使用)
    result['ps_ttm'] = merged['ps_ttm']

    # 4. market_cap - 总市值 (从万元转换为亿元)
    result['market_cap'] = merged['total_mv'] / 10000

    # 5. circ_market_cap - 流通市值 (从万元转换为亿元)
    result['circ_market_cap'] = merged['circ_mv'] / 10000

    # 只保留有足够历史数据的日期
    result = result.iloc[60:]

    return result


def create_valuation_factor_table():
    """创建估值因子表"""
    sql = """
    CREATE TABLE IF NOT EXISTS trade_stock_valuation_factor (
        id INT AUTO_INCREMENT PRIMARY KEY,
        stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
        calc_date DATE NOT NULL COMMENT '计算日期',
        pe_ttm DOUBLE COMMENT '市盈率TTM',
        pb DOUBLE COMMENT '市净率',
        ps_ttm DOUBLE COMMENT '市销率TTM',
        market_cap DOUBLE COMMENT '总市值(亿元)',
        circ_market_cap DOUBLE COMMENT '流通市值(亿元)',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_code_date (calc_date, stock_code),
        KEY idx_calc_date (calc_date),
        KEY idx_stock_code (stock_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票估值因子表';
    """
    conn, conn2 = get_dual_connections()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
    finally:
        conn.close()
    if conn2:
        try:
            cursor2 = conn2.cursor()
            cursor2.execute(sql)
            conn2.commit()
            cursor2.close()
        except Exception as e:
            logger.warning("Dual-write CREATE TABLE failed: %s", e)
        finally:
            conn2.close()
    logger.info("Valuation factor table ready: trade_stock_valuation_factor")


def get_col_value(row, col):
    """安全获取列值"""
    if col not in row.index:
        return None
    val = row[col]
    return float(val) if pd.notna(val) else None


def save_factors_batch(factors_data):
    """批量保存因子到数据库"""
    if not factors_data:
        return 0

    conn, conn2 = get_dual_connections()

    sql = """
        REPLACE INTO trade_stock_valuation_factor
        (stock_code, calc_date, pe_ttm, pb, ps_ttm, market_cap, circ_market_cap)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    records = []
    for code, factors_df in factors_data.items():
        for trade_date, row in factors_df.iterrows():
            records.append((
                code,
                trade_date.strftime('%Y-%m-%d'),
                get_col_value(row, 'pe_ttm'),
                get_col_value(row, 'pb'),
                get_col_value(row, 'ps_ttm'),
                get_col_value(row, 'market_cap'),
                get_col_value(row, 'circ_market_cap'),
            ))

    if not records:
        conn.close()
        if conn2:
            conn2.close()
        return 0

    # 分批插入
    batch_insert_size = 1000
    total_saved = 0
    for i in range(0, len(records), batch_insert_size):
        batch = records[i:i+batch_insert_size]
        try:
            cursor = conn.cursor()
            cursor.executemany(sql, batch)
            conn.commit()
            cursor.close()
            total_saved += len(batch)
        except Exception as e:
            logger.error(f"保存失败: {e}")

    conn.close()

    # Secondary write (best-effort)
    if conn2:
        try:
            for i in range(0, len(records), batch_insert_size):
                batch = records[i:i+batch_insert_size]
                cursor2 = conn2.cursor()
                cursor2.executemany(sql, batch)
                conn2.commit()
                cursor2.close()
        except Exception as e:
            logger.warning("Dual-write to %s failed: %s", 'secondary', e)
        finally:
            conn2.close()

    return len(records)


def main():
    """主函数 - 按股票分批回填估值因子（基本面数据按批加载，避免 OOM）"""
    logger.info("=" * 60)
    logger.info("估值因子计算程序")
    logger.info(f"回填范围: {START_DATE} ~ {END_DATE}")
    logger.info(f"数据加载范围: {DATA_START_DATE} ~ {END_DATE}")
    logger.info("=" * 60)

    # 1. 创建表
    logger.info(f"\n[1] 初始化估值因子表...")
    create_valuation_factor_table()

    # 2. 获取所有股票代码
    logger.info(f"\n[2] 获取股票列表...")
    all_codes = get_all_stock_codes()
    total_stocks = len(all_codes)
    logger.info(f"  共 {total_stocks} 只股票")

    # 3. 分批处理（基本面数据 + 日线数据同时按批加载）
    logger.info(f"\n[3] 开始分批处理 (每批 {BATCH_SIZE} 只股票)...")
    total_records = 0
    total_time_start = time()

    for batch_idx in range(0, total_stocks, BATCH_SIZE):
        batch_codes = all_codes[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1
        total_batches = (total_stocks + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info(f"\n--- 批次 {batch_num}/{total_batches} ({len(batch_codes)} 只股票) ---")

        # 加载基本面数据（仅当前批次）
        t0 = time()
        batch_basic = load_daily_basic_data(batch_codes, DATA_START_DATE, END_DATE)
        logger.info(f"  基本面数据: {len(batch_basic)} 只股票, {time()-t0:.1f}s")

        # 加载日线数据
        t0 = time()
        stock_data = load_stock_daily_data(batch_codes, DATA_START_DATE, END_DATE)
        logger.info(f"  日线数据: {len(stock_data)} 只股票, {time()-t0:.1f}s")

        if not stock_data:
            del batch_basic
            gc.collect()
            continue

        # 计算因子
        t0 = time()
        factors_data = {}
        for code, df in stock_data.items():
            try:
                basic_df = batch_basic.get(code)
                if basic_df is None or len(basic_df) == 0:
                    continue

                valuation_factors = calc_valuation_factors(df, basic_df)

                if valuation_factors is not None and not valuation_factors.empty:
                    start_dt = pd.to_datetime(START_DATE)
                    end_dt = pd.to_datetime(END_DATE)
                    mask = (valuation_factors.index >= start_dt) & (valuation_factors.index <= end_dt)
                    filtered = valuation_factors[mask]
                    if not filtered.empty:
                        factors_data[code] = filtered
            except Exception as e:
                logger.debug(f"  {code} 因子计算失败: {e}")

        logger.info(f"  因子计算完成: {len(factors_data)} 只股票有效, 耗时 {time()-t0:.1f}s")

        # 保存到数据库
        if factors_data:
            t0 = time()
            saved = save_factors_batch(factors_data)
            total_records += saved
            logger.info(f"  数据保存完成: {saved} 条记录, 耗时 {time()-t0:.1f}s")

        # 释放内存
        del batch_basic, stock_data, factors_data
        gc.collect()

        # 显示总进度
        elapsed = time() - total_time_start
        processed = min(batch_idx + BATCH_SIZE, total_stocks)
        speed = processed / elapsed if elapsed > 0 else 0
        eta = (total_stocks - processed) / speed / 60 if speed > 0 else 0

        logger.info(f"  >>> 总进度: {processed}/{total_stocks} 只股票 ({processed*100/total_stocks:.1f}%)")
        logger.info(f"  >>> 已保存: {total_records:,} 条记录")
        logger.info(f"  >>> 预计剩余时间: {eta:.1f} 分钟")

    # 4. 验证结果
    logger.info(f"\n[4] 验证结果...")
    sql = "SELECT COUNT(*) as cnt FROM trade_stock_valuation_factor"
    result = execute_query(sql)
    total = result[0]['cnt'] if result else 0
    logger.info(f"  估值因子表总记录数: {total:,}")

    sql = """
        SELECT calc_date, COUNT(*) as cnt
        FROM trade_stock_valuation_factor
        GROUP BY calc_date
        ORDER BY calc_date DESC
        LIMIT 5
    """
    result = execute_query(sql)
    logger.info(f"  最近5个交易日:")
    for r in result:
        logger.info(f"    {r['calc_date']}: {r['cnt']} 只股票")

    total_elapsed = time() - total_time_start
    logger.info(f"\n" + "=" * 60)
    logger.info(f"估值因子计算完成!")
    logger.info(f"  总耗时: {total_elapsed/60:.1f} 分钟")
    logger.info(f"  总记录数: {total_records:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
