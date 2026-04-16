# -*- coding: utf-8 -*-
"""
基础因子计算模块 - 第一批因子 (优化版)

优化: 一次性计算所有日期的因子，大幅减少数据加载时间

运行:
  # 计算今天的因子
  python data_analyst/factors/basic_factor_calculator.py

  # 回填历史数据 (从2024-01-01开始)
  python data_analyst/factors/basic_factor_calculator.py --backfill --start 2024-01-01
"""
import sys
import os
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


# ============================================================
# 数据加载
# ============================================================

def load_daily_data(start_date: str, end_date: str) -> dict:
    """批量加载日K线数据"""
    sql = """
        SELECT stock_code, trade_date, open_price, high_price, low_price,
               close_price, volume, amount, turnover_rate
        FROM trade_stock_daily
        WHERE trade_date >= %s AND trade_date <= %s
        ORDER BY stock_code, trade_date ASC
    """
    rows = execute_query(sql, [start_date, end_date])

    if not rows:
        logger.warning(f"未加载到数据: {start_date} ~ {end_date}")
        return {}

    df_all = pd.DataFrame(rows)
    df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])

    for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'amount', 'turnover_rate']:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce')

    result = {}
    codes = df_all['stock_code'].unique()

    for i, code in enumerate(codes):
        if (i + 1) % 1000 == 0:
            logger.info(f"  加载数据: {i+1}/{len(codes)}")

        group = df_all[df_all['stock_code'] == code]
        sub = group.set_index('trade_date').sort_index()
        result[code] = sub

    logger.info(f"加载完成: {len(result)} 只股票")
    return result


# ============================================================
# 因子计算
# ============================================================

def calc_factors_for_series(close: pd.Series, volume: pd.Series, turnover: pd.Series) -> pd.DataFrame:
    """
    计算单只股票所有日期的因子

    Args:
        close: 收盘价序列
        volume: 成交量序列
        turnover: 换手率序列

    Returns:
        DataFrame: 索引为日期，列为因子
    """
    df = pd.DataFrame(index=close.index)

    # 动量因子
    df['mom_20'] = close.pct_change(20)
    df['mom_60'] = close.pct_change(60)
    df['reversal_5'] = -close.pct_change(5)

    # 量价因子
    df['turnover'] = turnover
    vol_ma_5 = volume.rolling(5).mean()
    df['vol_ratio'] = volume / vol_ma_5.replace(0, np.nan)

    price_change = close.pct_change()
    vol_change = volume.pct_change()
    df['price_vol_diverge'] = price_change / (vol_change + 1e-10)

    # 波动率因子
    df['volatility_20'] = close.pct_change().rolling(20).std()

    # 收盘价
    df['close'] = close

    return df


def calc_all_factors_batch(all_data: dict, min_bars: int = 60) -> dict:
    """
    批量计算所有股票所有日期的因子

    Args:
        all_data: {stock_code: DataFrame}
        min_bars: 最小数据条数

    Returns:
        dict: {stock_code: DataFrame of factors}
    """
    result = {}
    codes = list(all_data.keys())
    total = len(codes)

    for i, code in enumerate(codes):
        if (i + 1) % 500 == 0:
            logger.info(f"  计算因子: {i+1}/{total}")

        df = all_data[code]
        if len(df) < min_bars:
            continue

        try:
            close = df['close_price']
            volume = df['volume']
            turnover = df['turnover_rate'] if 'turnover_rate' in df.columns else pd.Series(index=df.index)

            factors_df = calc_factors_for_series(close, volume, turnover)

            # 只保留有足够历史数据的日期（从第60个交易日开始）
            factors_df = factors_df.iloc[min_bars:]

            if not factors_df.empty:
                result[code] = factors_df
        except Exception as e:
            logger.debug(f"因子计算失败 {code}: {e}")
            continue

    logger.info(f"计算完成: {len(result)}/{total} 只股票有效")
    return result


# ============================================================
# 数据库操作
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_basic_factor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    calc_date DATE NOT NULL COMMENT '计算日期',
    mom_20 DOUBLE COMMENT '20日收益率',
    mom_60 DOUBLE COMMENT '60日收益率',
    reversal_5 DOUBLE COMMENT '5日反转因子',
    turnover DOUBLE COMMENT '换手率(%)',
    vol_ratio DOUBLE COMMENT '量比',
    price_vol_diverge DOUBLE COMMENT '价量背离',
    volatility_20 DOUBLE COMMENT '20日历史波动率',
    close DOUBLE COMMENT '收盘价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date (calc_date, stock_code),
    KEY idx_calc_date (calc_date),
    KEY idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票基础因子表';
"""


def create_factor_table():
    """创建因子表"""
    conn, conn2 = get_dual_connections()
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        cursor.close()
    finally:
        conn.close()
    if conn2:
        try:
            cursor2 = conn2.cursor()
            cursor2.execute(CREATE_TABLE_SQL)
            conn2.commit()
            cursor2.close()
        except Exception as e:
            logger.warning("Dual-write CREATE TABLE failed: %s", e)
        finally:
            conn2.close()
    logger.info("Factor table ready: trade_stock_basic_factor")


def save_factors_batch(all_factors: dict, batch_size: int = 5000) -> int:
    """
    批量保存所有因子到数据库

    Args:
        all_factors: {stock_code: DataFrame of factors}
        batch_size: 批量插入大小

    Returns:
        int: 保存的记录数
    """
    conn, conn2 = get_dual_connections()

    sql = """
        REPLACE INTO trade_stock_basic_factor
        (stock_code, calc_date, mom_20, mom_60, reversal_5,
         turnover, vol_ratio, price_vol_diverge, volatility_20, close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    total_records = 0
    batch = []
    total_stocks = len(all_factors)

    for i, (code, factors_df) in enumerate(all_factors.items()):
        if (i + 1) % 500 == 0:
            logger.info(f"  准备保存: {i+1}/{total_stocks} 只股票")

        for trade_date, row in factors_df.iterrows():
            batch.append((
                code,
                trade_date.strftime('%Y-%m-%d'),
                float(row['mom_20']) if pd.notna(row['mom_20']) else None,
                float(row['mom_60']) if pd.notna(row['mom_60']) else None,
                float(row['reversal_5']) if pd.notna(row['reversal_5']) else None,
                float(row['turnover']) if pd.notna(row['turnover']) else None,
                float(row['vol_ratio']) if pd.notna(row['vol_ratio']) else None,
                float(row['price_vol_diverge']) if pd.notna(row['price_vol_diverge']) else None,
                float(row['volatility_20']) if pd.notna(row['volatility_20']) else None,
                float(row['close']) if pd.notna(row['close']) else None,
            ))

            if len(batch) >= batch_size:
                try:
                    cursor = conn.cursor()
                    cursor.executemany(sql, batch)
                    conn.commit()
                    cursor.close()
                    total_records += len(batch)
                    logger.info(f"  保存进度: {total_records:,} 条记录")
                    if conn2:
                        dual_executemany(conn, conn2, sql, batch, _logger=logger)
                        conn2 = None  # closed by dual_executemany
                except Exception as e:
                    logger.error(f"批量保存失败: {e}")
                batch = []

    # 保存剩余
    if batch:
        try:
            cursor = conn.cursor()
            cursor.executemany(sql, batch)
            conn.commit()
            cursor.close()
            total_records += len(batch)
            if conn2:
                dual_executemany(conn, conn2, sql, batch, _logger=logger)
                conn2 = None
        except Exception as e:
            logger.error(f"保存失败: {e}")

    conn.close()
    if conn2:
        conn2.close()

    return total_records


# ============================================================
# 主流程
# ============================================================

def calculate_and_save_factors(calc_date=None, start_date=None):
    """
    计算并保存单日因子 (增量模式: 分批加载, 只计算目标日期)

    Args:
        calc_date: 目标日期, 默认今天
        start_date: K线加载起始日期. 默认自动计算(目标日期前120自然日,
                    足够 mom_60 等滚动窗口)
    """
    if calc_date is None:
        calc_date = date.today()
    end_str = calc_date.strftime('%Y-%m-%d') if hasattr(calc_date, 'strftime') else str(calc_date)

    # 增量: 只回填目标日期一天, 用 backfill 的分批模式
    backfill_factors(start_date=end_str, end_date=end_str, batch_size=200)


def backfill_factors(start_date='2024-01-01', end_date=None, batch_size=500):
    """
    回填历史因子数据 (分批模式: 每批 batch_size 只股票，避免 OOM)

    每批加载该批股票从 data_start 到 end_date 的数据，计算后只保存
    start_date ~ end_date 范围内的因子，然后释放内存继续下一批。
    """
    if end_date is None:
        end_date = date.today()

    # 计算因子需要足够的历史数据（mom_60 需要60个交易日）
    # 取 start_date 往前推120个自然日作为数据加载起点
    start_dt = pd.to_datetime(start_date)
    data_start = (start_dt - pd.Timedelta(days=120)).strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else str(end_date)

    logger.info("=" * 60)
    logger.info("因子回填程序 (分批模式)")
    logger.info(f"回填范围: {start_date} ~ {end_str}")
    logger.info(f"数据加载起点: {data_start}")
    logger.info(f"每批股票数: {batch_size}")
    logger.info("=" * 60)

    create_factor_table()

    # 获取全部股票代码
    codes_result = execute_query("SELECT DISTINCT stock_code FROM trade_stock_basic ORDER BY stock_code")
    all_codes = [r['stock_code'] for r in codes_result] if codes_result else []
    total = len(all_codes)
    logger.info(f"共 {total} 只股票，分 {(total + batch_size - 1) // batch_size} 批处理")

    total_saved = 0
    start_dt_filter = pd.to_datetime(start_date)
    end_dt_filter = pd.to_datetime(end_str)

    for batch_idx in range(0, total, batch_size):
        batch_codes = all_codes[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        logger.info(f"\n--- 批次 {batch_num}/{total_batches} ({len(batch_codes)} 只股票) ---")

        # 只加载本批股票的数据
        placeholders = ','.join(['%s'] * len(batch_codes))
        sql = f"""
            SELECT stock_code, trade_date, open_price, high_price, low_price,
                   close_price, volume, amount, turnover_rate
            FROM trade_stock_daily
            WHERE trade_date >= %s AND trade_date <= %s
              AND stock_code IN ({placeholders})
            ORDER BY stock_code, trade_date ASC
        """
        params = [data_start, end_str] + batch_codes
        t0 = time()
        rows = execute_query(sql, params)
        if not rows:
            logger.warning(f"  批次 {batch_num}: 无数据，跳过")
            continue

        df_all = pd.DataFrame(rows)
        df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
        for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'amount', 'turnover_rate']:
            if col in df_all.columns:
                df_all[col] = pd.to_numeric(df_all[col], errors='coerce')

        batch_data = {}
        for code in df_all['stock_code'].unique():
            group = df_all[df_all['stock_code'] == code]
            batch_data[code] = group.set_index('trade_date').sort_index()
        logger.info(f"  加载完成: {len(batch_data)} 只股票, {time()-t0:.1f}s")

        # 计算因子
        t0 = time()
        all_factors = calc_all_factors_batch(batch_data)
        logger.info(f"  因子计算: {len(all_factors)} 只股票, {time()-t0:.1f}s")

        # 过滤目标日期范围
        filtered = {}
        for code, fdf in all_factors.items():
            mask = (fdf.index >= start_dt_filter) & (fdf.index <= end_dt_filter)
            sub = fdf[mask]
            if not sub.empty:
                filtered[code] = sub

        # 保存
        t0 = time()
        saved = save_factors_batch(filtered)
        total_saved += saved
        logger.info(f"  保存: {saved} 条, {time()-t0:.1f}s  (累计 {total_saved:,})")

        # 释放内存
        del df_all, batch_data, all_factors, filtered

    # 验证
    logger.info(f"\n[验证] 查询因子表...")
    sql = """
        SELECT calc_date, COUNT(*) as cnt
        FROM trade_stock_basic_factor
        GROUP BY calc_date
        ORDER BY calc_date DESC
        LIMIT 5
    """
    result = execute_query(sql)
    logger.info("最近5个交易日:")
    for r in result:
        logger.info(f"  {r['calc_date']}: {r['cnt']} 只股票")

    logger.info("\n" + "=" * 60)
    logger.info(f"因子回填完成! 共写入 {total_saved:,} 条记录")
    logger.info("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='基础因子计算')
    parser.add_argument('--backfill', action='store_true', help='回填历史数据')
    parser.add_argument('--start', type=str, default='2024-01-01', help='回填起始日期')
    args = parser.parse_args()

    if args.backfill:
        backfill_factors(start_date=args.start)
    else:
        calculate_and_save_factors()


if __name__ == "__main__":
    main()
