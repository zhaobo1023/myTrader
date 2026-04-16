# -*- coding: utf-8 -*-
"""
财务质量因子计算模块

补充因子:
- quality类: cash_flow_ratio, accrual, current_ratio, roa, debt_ratio

运行:
  # 计算今天的因子
  python data_analyst/factors/quality_factor_calculator.py

  # 回填历史数据
  python data_analyst/factors/quality_factor_calculator.py --backfill --start 2024-01-01
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
# 质量因子需要日线+财务数据, 180自然日足够覆盖滚动窗口
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


def load_financial_data(stock_codes):
    """加载财务数据"""
    if not stock_codes:
        return {}

    placeholders = ', '.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, report_date, roe, roa, net_profit, revenue,
               gross_margin, operating_cashflow, total_assets, total_equity,
               current_ratio, debt_ratio
        FROM trade_stock_financial
        WHERE stock_code IN ({placeholders})
        ORDER BY stock_code, report_date ASC
    """
    rows = execute_query(sql, stock_codes)

    if not rows:
        return {}

    df = pd.DataFrame(rows)
    df['report_date'] = pd.to_datetime(df['report_date'])

    # 转换数值
    for col in ['roe', 'roa', 'net_profit', 'revenue', 'gross_margin', 'operating_cashflow',
                'total_assets', 'total_equity', 'current_ratio', 'debt_ratio']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    result = {}
    for code in stock_codes:
        group = df[df['stock_code'] == code]
        if len(group) > 0:
            sub = group.set_index('report_date').sort_index()
            result[code] = sub

    return result


def calc_quality_factors(daily_df, financial_df):
    """
    计算财务质量因子

    Args:
        daily_df: 日线数据
        financial_df: 财务数据

    Returns:
        DataFrame: 质量因子
    """
    if financial_df is None or len(financial_df) < 4:
        return None

    result = pd.DataFrame(index=daily_df.index)

    # 重置索引以便合并
    fin = financial_df.reset_index()
    fin = fin.rename(columns={'report_date': 'trade_date'})

    # 创建交易日历
    daily_dates = daily_df.index.to_frame(index=False)
    daily_dates['trade_date'] = pd.to_datetime(daily_dates['trade_date'])

    # 使用 asof 合并 (向前查找最近的报告)
    daily_dates_sorted = daily_dates.sort_values('trade_date')
    fin_sorted = fin.sort_values('trade_date')

    merged = pd.merge_asof(
        daily_dates_sorted,
        fin_sorted,
        on='trade_date',
        direction='backward'
    )
    merged = merged.set_index('trade_date')

    # 1. ROA - 资产收益率 (直接使用)
    result['roa'] = merged['roa']

    # 2. current_ratio - 流动比率 (直接使用)
    result['current_ratio'] = merged['current_ratio']

    # 3. debt_ratio - 资产负债率 (直接使用)
    result['debt_ratio'] = merged['debt_ratio']

    # 4. cash_flow_ratio - 经营现金流/净利润 (盈余质量)
    net_profit = merged['net_profit']
    operating_cashflow = merged['operating_cashflow']
    result['cash_flow_ratio'] = np.where(
        (net_profit.notna() & (net_profit != 0)),
        operating_cashflow / net_profit,
        np.nan
    )

    # 5. accrual - 应计项目比率 (净利润 - 经营现金流) / 总资产
    # 衡量盈余质量，值越大表示盈余质量越差
    total_assets = merged['total_assets']
    result['accrual'] = np.where(
        (total_assets.notna() & (total_assets != 0)),
        (net_profit - operating_cashflow) / total_assets,
        np.nan
    )

    # 只保留有足够历史数据的日期
    result = result.iloc[60:]

    return result


def create_quality_factor_table():
    """创建质量因子表"""
    sql = """
    CREATE TABLE IF NOT EXISTS trade_stock_quality_factor (
        id INT AUTO_INCREMENT PRIMARY KEY,
        stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
        calc_date DATE NOT NULL COMMENT '计算日期',
        cash_flow_ratio DOUBLE COMMENT '现金流/净利润(盈余质量)',
        accrual DOUBLE COMMENT '应计项目比率',
        current_ratio DOUBLE COMMENT '流动比率',
        roa DOUBLE COMMENT '资产收益率(%)',
        debt_ratio DOUBLE COMMENT '资产负债率(%)',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_code_date (calc_date, stock_code),
        KEY idx_calc_date (calc_date),
        KEY idx_stock_code (stock_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票质量因子表';
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
    logger.info("Quality factor table ready: trade_stock_quality_factor")


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
        REPLACE INTO trade_stock_quality_factor
        (stock_code, calc_date, cash_flow_ratio, accrual, current_ratio, roa, debt_ratio)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    records = []
    for code, factors_df in factors_data.items():
        for trade_date, row in factors_df.iterrows():
            records.append((
                code,
                trade_date.strftime('%Y-%m-%d'),
                get_col_value(row, 'cash_flow_ratio'),
                get_col_value(row, 'accrual'),
                get_col_value(row, 'current_ratio'),
                get_col_value(row, 'roa'),
                get_col_value(row, 'debt_ratio'),
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
    """主函数 - 按股票分批回填质量因子（财务数据按批加载，避免 OOM）"""
    logger.info("=" * 60)
    logger.info("财务质量因子计算程序")
    logger.info(f"回填范围: {START_DATE} ~ {END_DATE}")
    logger.info(f"数据加载范围: {DATA_START_DATE} ~ {END_DATE}")
    logger.info("=" * 60)

    # 1. 创建表
    logger.info(f"\n[1] 初始化质量因子表...")
    create_quality_factor_table()

    # 2. 获取所有股票代码
    logger.info(f"\n[2] 获取股票列表...")
    all_codes = get_all_stock_codes()
    total_stocks = len(all_codes)
    logger.info(f"  共 {total_stocks} 只股票")

    # 3. 分批处理（财务数据 + 日线数据同时按批加载）
    logger.info(f"\n[3] 开始分批处理 (每批 {BATCH_SIZE} 只股票)...")
    total_records = 0
    total_time_start = time()

    for batch_idx in range(0, total_stocks, BATCH_SIZE):
        batch_codes = all_codes[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1
        total_batches = (total_stocks + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info(f"\n--- 批次 {batch_num}/{total_batches} ({len(batch_codes)} 只股票) ---")

        # 加载财务数据（仅当前批次）
        t0 = time()
        batch_financial = load_financial_data(batch_codes)
        logger.info(f"  财务数据: {len(batch_financial)} 只股票, {time()-t0:.1f}s")

        # 加载日线数据
        t0 = time()
        stock_data = load_stock_daily_data(batch_codes, DATA_START_DATE, END_DATE)
        logger.info(f"  日线数据: {len(stock_data)} 只股票, {time()-t0:.1f}s")

        if not stock_data:
            del batch_financial
            gc.collect()
            continue

        # 计算因子
        t0 = time()
        factors_data = {}
        for code, df in stock_data.items():
            try:
                financial_df = batch_financial.get(code)
                quality_factors = calc_quality_factors(df, financial_df) if financial_df is not None else None

                if quality_factors is not None and not quality_factors.empty:
                    start_dt = pd.to_datetime(START_DATE)
                    end_dt = pd.to_datetime(END_DATE)
                    mask = (quality_factors.index >= start_dt) & (quality_factors.index <= end_dt)
                    filtered = quality_factors[mask]
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
        del batch_financial, stock_data, factors_data
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
    sql = "SELECT COUNT(*) as cnt FROM trade_stock_quality_factor"
    result = execute_query(sql)
    total = result[0]['cnt'] if result else 0
    logger.info(f"  质量因子表总记录数: {total:,}")

    sql = """
        SELECT calc_date, COUNT(*) as cnt
        FROM trade_stock_quality_factor
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
    logger.info(f"质量因子计算完成!")
    logger.info(f"  总耗时: {total_elapsed/60:.1f} 分钟")
    logger.info(f"  总记录数: {total_records:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
