# -*- coding: utf-8 -*-
"""
扩展因子计算模块 - 第二批因子

补充因子:
- 量价延伸: mom_5, mom_10, reversal_1, turnover_20_mean, amihud_illiquidity, high_low_ratio, volume_ratio_20
- 财务类: roe_ttm, gross_margin, net_profit_growth, revenue_growth

运行:
  # 计算今天的因子
  python data_analyst/factors/extended_factor_calculator.py

  # 回填历史数据
  python data_analyst/factors/extended_factor_calculator.py --backfill --start 2024-01-01
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


# 配置（可被命令行参数覆盖）
BATCH_SIZE = 500  # 每批处理的股票数量
START_DATE = date.today().strftime('%Y-%m-%d')  # 默认只算今天
END_DATE = date.today().strftime('%Y-%m-%d')
# 因子计算需要约120个交易日(~180自然日)的历史数据作为滚动窗口
DATA_START_DATE = (date.today() - timedelta(days=180)).strftime('%Y-%m-%d')


def get_all_stock_codes():
    """获取所有股票代码"""
    sql = "SELECT DISTINCT stock_code FROM trade_stock_daily ORDER BY stock_code"
    rows = execute_query(sql)
    return [r['stock_code'] for r in rows]


def load_daily_data_batched(all_codes, start_date, end_date, batch_size=1000, env='online'):
    """分批加载全市场日线数据，合并为单个 DataFrame"""
    frames = []
    total_batches = (len(all_codes) + batch_size - 1) // batch_size

    for i in range(0, len(all_codes), batch_size):
        batch_codes = all_codes[i:i + batch_size]
        batch_num = i // batch_size + 1
        ph = ','.join(['%s'] * len(batch_codes))
        sql = f"""
            SELECT stock_code, trade_date, open_price, high_price, low_price,
                   close_price, volume, amount, turnover_rate
            FROM trade_stock_daily
            WHERE stock_code IN ({ph})
              AND trade_date >= %s AND trade_date <= %s
            ORDER BY stock_code, trade_date ASC
        """
        rows = execute_query(sql, batch_codes + [start_date, end_date], env=env)
        if rows:
            frames.append(pd.DataFrame(rows))
            logger.info(f"  日线数据批次 {batch_num}/{total_batches}: "
                        f"{len(rows)} 行 (累计 {sum(len(f) for f in frames)})")

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    for col in ['open_price', 'high_price', 'low_price', 'close_price',
                'volume', 'amount', 'turnover_rate']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.sort_values(['stock_code', 'trade_date']).reset_index(drop=True)
    return df


def load_financial_data_batched(all_codes, batch_size=1000, env='online'):
    """分批加载全市场财务数据，合并为单个 DataFrame"""
    frames = []
    total_batches = (len(all_codes) + batch_size - 1) // batch_size

    for i in range(0, len(all_codes), batch_size):
        batch_codes = all_codes[i:i + batch_size]
        batch_num = i // batch_size + 1
        ph = ','.join(['%s'] * len(batch_codes))
        sql = f"""
            SELECT stock_code, report_date, roe, net_profit, revenue,
                   gross_margin, operating_cashflow, eps, total_equity
            FROM trade_stock_financial
            WHERE stock_code IN ({ph})
            ORDER BY stock_code, report_date ASC
        """
        rows = execute_query(sql, batch_codes, env=env)
        if rows:
            frames.append(pd.DataFrame(rows))
            logger.info(f"  财务数据批次 {batch_num}/{total_batches}: "
                        f"{len(rows)} 行 (累计 {sum(len(f) for f in frames)})")

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df['report_date'] = pd.to_datetime(df['report_date'])
    for col in ['roe', 'net_profit', 'revenue', 'gross_margin',
                'operating_cashflow', 'eps', 'total_equity']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.sort_values(['stock_code', 'report_date']).reset_index(drop=True)
    return df


# --- Legacy per-stock loading (kept for backward compatibility) ---

def load_stock_daily_data(stock_codes, start_date, end_date):
    """批量加载指定股票的K线数据 (dict格式, 旧接口)"""
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
    """加载财务数据 (dict格式, 旧接口)"""
    if not stock_codes:
        return {}

    placeholders = ', '.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, report_date, roe, net_profit, revenue,
               gross_margin, operating_cashflow, eps, total_equity
        FROM trade_stock_financial
        WHERE stock_code IN ({placeholders})
        ORDER BY stock_code, report_date ASC
    """
    rows = execute_query(sql, stock_codes)

    if not rows:
        return {}

    df = pd.DataFrame(rows)
    df['report_date'] = pd.to_datetime(df['report_date'])

    for col in ['roe', 'net_profit', 'revenue', 'gross_margin', 'operating_cashflow', 'eps', 'total_equity']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    result = {}
    for code in stock_codes:
        group = df[df['stock_code'] == code]
        if len(group) > 0:
            sub = group.set_index('report_date').sort_index()
            result[code] = sub

    return result


def calc_price_volume_factors(df):
    """计算量价类因子"""
    if len(df) < 60:
        return None

    close = df['close_price']
    high = df['high_price']
    low = df['low_price']
    volume = df['volume']
    amount = df['amount']
    turnover = df['turnover_rate'] if 'turnover_rate' in df.columns else pd.Series(index=df.index)

    result = pd.DataFrame(index=df.index)

    # 1. 短期动量因子
    result['mom_5'] = close.pct_change(5)
    result['mom_10'] = close.pct_change(10)

    # 2. 1日反转因子 (负收益表示反转)
    result['reversal_1'] = -close.pct_change(1)

    # 3. 20日平均换手率
    result['turnover_20_mean'] = turnover.rolling(20).mean()

    # 4. Amihud 非流动性因子 = |收益| / 成交额
    daily_return = close.pct_change().abs()
    amount_safe = amount.replace(0, np.nan)
    result['amihud_illiquidity'] = (daily_return / amount_safe * 1e8).rolling(20).mean()

    # 5. 日内振幅 = (high - low) / close
    result['high_low_ratio'] = (high - low) / close

    # 6. 成交量比 = 当日成交量 / 20日平均成交量
    vol_ma_20 = volume.rolling(20).mean()
    result['volume_ratio_20'] = volume / vol_ma_20.replace(0, np.nan)

    # 保留足够历史数据的日期
    result = result.iloc[60:]

    return result


def calc_financial_factors(daily_df, financial_df):
    """计算财务类因子 (TTM和增长率)"""
    if financial_df is None or len(financial_df) < 4:
        return None

    result = pd.DataFrame(index=daily_df.index)

    # 获取最近的财务数据 (向前填充)
    # 财务数据是季度报告，需要映射到每个交易日

    # 重置索引以便合并
    fin = financial_df.reset_index()
    fin = fin.rename(columns={'report_date': 'trade_date'})

    # 创建交易日历
    daily_dates = daily_df.index.to_frame(index=False)
    daily_dates['trade_date'] = pd.to_datetime(daily_dates['trade_date'])

    # 对于每个交易日，找到最近的财务报告
    fin_expanded = pd.DataFrame(index=daily_df.index)

    # 使用 asof 合并 (向前查找最近的报告)
    daily_dates_sorted = daily_dates.sort_values('trade_date')
    fin_sorted = fin.sort_values('trade_date')

    # 合并
    merged = pd.merge_asof(
        daily_dates_sorted,
        fin_sorted,
        on='trade_date',
        direction='backward'  # 向前查找
    )
    merged = merged.set_index('trade_date')

    # 1. ROE_TTM (最近4个季度的ROE累加，简化处理用最新ROE)
    # 注意: 这里简化处理，实际应该用TTM计算
    fin_expanded['roe_ttm'] = merged['roe']

    # 2. 毛利率
    fin_expanded['gross_margin'] = merged['gross_margin']

    # 3. 净利润增长率 (同比)
    # 需要计算 YoY 增长，简化处理
    net_profit = financial_df['net_profit'].dropna()
    if len(net_profit) >= 5:  # 至少需要5个报告期来计算同比
        # 按季度对齐计算同比
        yoy_growth = net_profit.pct_change(4)  # 4个季度前
        yoy_df = pd.DataFrame({'net_profit_growth': yoy_growth})

        # 同样需要映射到交易日
        yoy_df = yoy_df.reset_index()
        yoy_df = yoy_df.rename(columns={'report_date': 'trade_date'})

        merged_yoy = pd.merge_asof(
            daily_dates_sorted,
            yoy_df,
            on='trade_date',
            direction='backward'
        )
        merged_yoy = merged_yoy.set_index('trade_date')
        fin_expanded['net_profit_growth'] = merged_yoy['net_profit_growth']

    # 4. 营收增长率 (同比)
    revenue = financial_df['revenue'].dropna()
    if len(revenue) >= 5:
        yoy_growth = revenue.pct_change(4)
        yoy_df = pd.DataFrame({'revenue_growth': yoy_growth})
        yoy_df = yoy_df.reset_index()
        yoy_df = yoy_df.rename(columns={'report_date': 'trade_date'})

        merged_yoy = pd.merge_asof(
            daily_dates_sorted,
            yoy_df,
            on='trade_date',
            direction='backward'
        )
        merged_yoy = merged_yoy.set_index('trade_date')
        fin_expanded['revenue_growth'] = merged_yoy['revenue_growth']

    # 只保留有足够历史数据的日期
    fin_expanded = fin_expanded.iloc[60:]

    return fin_expanded


def merge_and_prepare_factors(price_factors, financial_factors, stock_code):
    """合并量价因子和财务因子"""
    if price_factors is None:
        return None

    if financial_factors is None:
        # 只有量价因子
        result = price_factors.copy()
        # 添加财务因子列为 NaN
        fin_cols = ['roe_ttm', 'gross_margin', 'net_profit_growth', 'revenue_growth']
        for col in fin_cols:
            result[col] = np.nan
        return result

    # 合并
    result = price_factors.join(financial_factors, how='left')

    # 确保所有列都存在
    required_cols = ['mom_5', 'mom_10', 'reversal_1', 'turnover_20_mean',
                     'amihud_illiquidity', 'high_low_ratio', 'volume_ratio_20',
                     'roe_ttm', 'gross_margin', 'net_profit_growth', 'revenue_growth']
    for col in required_cols:
        if col not in result.columns:
            result[col] = np.nan

    return result


def create_extended_factor_table():
    """创建扩展因子表"""
    sql = """
    CREATE TABLE IF NOT EXISTS trade_stock_extended_factor (
        id INT AUTO_INCREMENT PRIMARY KEY,
        stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
        calc_date DATE NOT NULL COMMENT '计算日期',
        mom_5 DOUBLE COMMENT '5日收益率',
        mom_10 DOUBLE COMMENT '10日收益率',
        reversal_1 DOUBLE COMMENT '1日反转因子',
        turnover_20_mean DOUBLE COMMENT '20日平均换手率(%)',
        amihud_illiquidity DOUBLE COMMENT 'Amihud非流动性因子',
        high_low_ratio DOUBLE COMMENT '日内振幅',
        volume_ratio_20 DOUBLE COMMENT '20日量比',
        roe_ttm DOUBLE COMMENT 'ROE(TTM)',
        gross_margin DOUBLE COMMENT '毛利率(%)',
        net_profit_growth DOUBLE COMMENT '净利润同比增速(%)',
        revenue_growth DOUBLE COMMENT '营收同比增速(%)',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_code_date (calc_date, stock_code),
        KEY idx_calc_date (calc_date),
        KEY idx_stock_code (stock_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票扩展因子表';
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
    logger.info("Extended factor table ready: trade_stock_extended_factor")


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
        REPLACE INTO trade_stock_extended_factor
        (stock_code, calc_date, mom_5, mom_10, reversal_1,
         turnover_20_mean, amihud_illiquidity, high_low_ratio, volume_ratio_20,
         roe_ttm, gross_margin, net_profit_growth, revenue_growth)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    records = []
    for code, factors_df in factors_data.items():
        for trade_date, row in factors_df.iterrows():
            records.append((
                code,
                trade_date.strftime('%Y-%m-%d'),
                get_col_value(row, 'mom_5'),
                get_col_value(row, 'mom_10'),
                get_col_value(row, 'reversal_1'),
                get_col_value(row, 'turnover_20_mean'),
                get_col_value(row, 'amihud_illiquidity'),
                get_col_value(row, 'high_low_ratio'),
                get_col_value(row, 'volume_ratio_20'),
                get_col_value(row, 'roe_ttm'),
                get_col_value(row, 'gross_margin'),
                get_col_value(row, 'net_profit_growth'),
                get_col_value(row, 'revenue_growth'),
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


def calc_price_volume_factors_vectorized(df):
    """
    向量化计算全市场量价因子

    Args:
        df: DataFrame with columns [stock_code, trade_date, close_price,
            high_price, low_price, volume, amount, turnover_rate]
            sorted by [stock_code, trade_date]

    Returns:
        DataFrame with factor columns added, same rows as input
    """
    g = df.groupby('stock_code')

    df['mom_5'] = g['close_price'].transform(lambda x: x.pct_change(5))
    df['mom_10'] = g['close_price'].transform(lambda x: x.pct_change(10))
    df['reversal_1'] = -g['close_price'].transform(lambda x: x.pct_change(1))
    df['turnover_20_mean'] = g['turnover_rate'].transform(
        lambda x: x.rolling(20, min_periods=20).mean()
    )

    # Amihud: |return| / amount * 1e8, rolling 20-day mean
    daily_ret_abs = g['close_price'].transform(lambda x: x.pct_change().abs())
    amount_safe = df['amount'].replace(0, np.nan)
    raw_amihud = daily_ret_abs / amount_safe * 1e8
    df['amihud_illiquidity'] = raw_amihud.groupby(df['stock_code']).transform(
        lambda x: x.rolling(20, min_periods=20).mean()
    )

    df['high_low_ratio'] = (df['high_price'] - df['low_price']) / df['close_price']

    vol_ma_20 = g['volume'].transform(lambda x: x.rolling(20, min_periods=20).mean())
    df['volume_ratio_20'] = df['volume'] / vol_ma_20.replace(0, np.nan)

    return df


def calc_financial_factors_vectorized(daily_df, fin_df):
    """
    向量化计算全市场财务因子

    对每只股票的每个交易日，用 merge_asof(by='stock_code') 找到最近的财报数据,
    然后计算 roe_ttm, gross_margin, net_profit_growth, revenue_growth。

    Args:
        daily_df: DataFrame with [stock_code, trade_date] (sorted)
        fin_df: DataFrame with [stock_code, report_date, roe, ...]

    Returns:
        DataFrame with financial factor columns, indexed same as daily_df
    """
    if fin_df.empty:
        daily_df['roe_ttm'] = np.nan
        daily_df['gross_margin'] = np.nan
        daily_df['net_profit_growth'] = np.nan
        daily_df['revenue_growth'] = np.nan
        return daily_df

    fin = fin_df.copy()
    fin = fin.rename(columns={'report_date': 'trade_date'})

    # Compute YoY growth per stock before merge
    fin = fin.sort_values(['stock_code', 'trade_date'])
    fin['net_profit_growth'] = fin.groupby('stock_code')['net_profit'].transform(
        lambda x: x.pct_change(4)
    )
    fin['revenue_growth'] = fin.groupby('stock_code')['revenue'].transform(
        lambda x: x.pct_change(4)
    )

    fin_merge = fin[['stock_code', 'trade_date', 'roe', 'gross_margin',
                      'net_profit_growth', 'revenue_growth']].copy()
    # merge_asof requires the 'on' key to be sorted globally
    fin_merge = fin_merge.sort_values('trade_date')

    # Use merge_asof with by='stock_code' for vectorized per-stock lookup
    daily_sorted = daily_df[['stock_code', 'trade_date']].copy()
    daily_sorted = daily_sorted.sort_values('trade_date')

    merged = pd.merge_asof(
        daily_sorted,
        fin_merge,
        on='trade_date',
        by='stock_code',
        direction='backward'
    )
    merged = merged.rename(columns={'roe': 'roe_ttm'})

    daily_df = daily_df.merge(
        merged[['stock_code', 'trade_date', 'roe_ttm', 'gross_margin',
                 'net_profit_growth', 'revenue_growth']],
        on=['stock_code', 'trade_date'],
        how='left'
    )

    return daily_df


def save_factors_dataframe(df, env='online'):
    """
    批量保存因子 DataFrame 到数据库

    Args:
        df: DataFrame with columns [stock_code, trade_date, factor_columns...]
        env: 数据库环境

    Returns:
        写入行数
    """
    factor_cols = ['mom_5', 'mom_10', 'reversal_1', 'turnover_20_mean',
                   'amihud_illiquidity', 'high_low_ratio', 'volume_ratio_20',
                   'roe_ttm', 'gross_margin', 'net_profit_growth', 'revenue_growth']

    out = df[['stock_code', 'trade_date'] + factor_cols].copy()
    out['trade_date'] = pd.to_datetime(out['trade_date']).dt.strftime('%Y-%m-%d')

    # NaN/inf -> None for SQL
    out = out.replace({np.nan: None, np.inf: None, -np.inf: None})

    records = list(out.itertuples(index=False, name=None))

    sql = """
        REPLACE INTO trade_stock_extended_factor
        (stock_code, calc_date, mom_5, mom_10, reversal_1,
         turnover_20_mean, amihud_illiquidity, high_low_ratio, volume_ratio_20,
         roe_ttm, gross_margin, net_profit_growth, revenue_growth)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    conn, conn2 = get_dual_connections(primary_env=env)
    total_saved = 0
    batch_insert_size = 2000

    try:
        cursor = conn.cursor()
        for i in range(0, len(records), batch_insert_size):
            batch = records[i:i + batch_insert_size]
            cursor.executemany(sql, batch)
            conn.commit()
            total_saved += len(batch)
        cursor.close()
    except Exception as e:
        logger.error(f"Primary write failed: {e}")
    finally:
        conn.close()

    if conn2:
        try:
            cursor2 = conn2.cursor()
            for i in range(0, len(records), batch_insert_size):
                batch = records[i:i + batch_insert_size]
                cursor2.executemany(sql, batch)
                conn2.commit()
            cursor2.close()
        except Exception as e:
            logger.warning("Dual-write failed: %s", e)
        finally:
            conn2.close()

    return total_saved


def main():
    """主函数 - 全市场向量化计算扩展因子"""
    import argparse as _ap
    parser = _ap.ArgumentParser(description='扩展因子计算')
    parser.add_argument('--start', type=str, default=None, help='回填起始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, default=None, help='回填结束日期 YYYY-MM-DD')
    parser.add_argument('--env', type=str, default='online', help='数据库环境')
    args = parser.parse_args()

    global START_DATE, END_DATE, DATA_START_DATE
    if args.start:
        START_DATE = args.start
        data_start_dt = pd.to_datetime(START_DATE) - pd.Timedelta(days=180)
        DATA_START_DATE = data_start_dt.strftime('%Y-%m-%d')
    if args.end:
        END_DATE = args.end

    env = args.env

    logger.info("=" * 60)
    logger.info("扩展因子计算程序（向量化模式）")
    logger.info(f"回填范围: {START_DATE} ~ {END_DATE}")
    logger.info(f"数据加载范围: {DATA_START_DATE} ~ {END_DATE}")
    logger.info("=" * 60)

    t_total = time()

    # 1. 创建表
    logger.info("[1] 初始化扩展因子表...")
    create_extended_factor_table()

    # 2. 获取所有股票代码
    logger.info("[2] 获取股票列表...")
    all_codes = get_all_stock_codes()
    logger.info(f"  共 {len(all_codes)} 只股票")

    # 3. 分批加载全市场日线数据
    logger.info("[3] 加载全市场日线数据...")
    t0 = time()
    daily_df = load_daily_data_batched(all_codes, DATA_START_DATE, END_DATE, env=env)
    if daily_df.empty:
        logger.error("无日线数据")
        return
    t1 = time()
    logger.info(f"  日线数据加载完成: {len(daily_df)} 行, {daily_df['stock_code'].nunique()} 只股票, "
                f"耗时 {t1-t0:.1f}s")

    # 4. 分批加载全市场财务数据
    logger.info("[4] 加载全市场财务数据...")
    fin_df = load_financial_data_batched(all_codes, env=env)
    t2 = time()
    logger.info(f"  财务数据加载完成: {len(fin_df)} 行, "
                f"{fin_df['stock_code'].nunique() if not fin_df.empty else 0} 只股票, "
                f"耗时 {t2-t1:.1f}s")

    # 5. 过滤数据不足的股票 (< 60 交易日)
    stock_counts = daily_df.groupby('stock_code').size()
    valid_stocks = stock_counts[stock_counts >= 60].index
    daily_df = daily_df[daily_df['stock_code'].isin(valid_stocks)].copy()
    logger.info(f"  过滤后: {daily_df['stock_code'].nunique()} 只股票 "
                f"(去除 {len(stock_counts) - len(valid_stocks)} 只数据不足)")

    # 6. 向量化计算量价因子
    logger.info("[5] 计算量价因子...")
    t3 = time()
    daily_df = calc_price_volume_factors_vectorized(daily_df)
    t4 = time()
    logger.info(f"  量价因子计算完成, 耗时 {t4-t3:.1f}s")

    # 7. 向量化计算财务因子
    logger.info("[6] 计算财务因子...")
    daily_df = calc_financial_factors_vectorized(daily_df, fin_df)
    t5 = time()
    logger.info(f"  财务因子计算完成, 耗时 {t5-t4:.1f}s")
    del fin_df
    gc.collect()

    # 8. 过滤日期范围 (只保留回填范围内的数据)
    start_dt = pd.to_datetime(START_DATE)
    end_dt = pd.to_datetime(END_DATE)
    output_df = daily_df[
        (daily_df['trade_date'] >= start_dt) & (daily_df['trade_date'] <= end_dt)
    ].copy()
    logger.info(f"  输出范围: {len(output_df)} 行, "
                f"{output_df['stock_code'].nunique()} 只股票")

    del daily_df
    gc.collect()

    if output_df.empty:
        logger.info("无数据需要写入")
        return

    # 9. 保存到数据库
    logger.info("[7] 保存到数据库...")
    t6 = time()
    total_records = save_factors_dataframe(output_df, env=env)
    t7 = time()
    logger.info(f"  保存完成: {total_records} 条记录, 耗时 {t7-t6:.1f}s")

    # 10. 验证结果
    logger.info("[8] 验证结果...")
    sql = "SELECT COUNT(*) as cnt FROM trade_stock_extended_factor"
    result = execute_query(sql, env=env)
    total = result[0]['cnt'] if result else 0
    logger.info(f"  扩展因子表总记录数: {total:,}")

    sql = """
        SELECT calc_date, COUNT(*) as cnt
        FROM trade_stock_extended_factor
        GROUP BY calc_date
        ORDER BY calc_date DESC
        LIMIT 5
    """
    result = execute_query(sql, env=env)
    logger.info("  最近5个交易日:")
    for r in result:
        logger.info(f"    {r['calc_date']}: {r['cnt']} 只股票")

    total_elapsed = time() - t_total
    logger.info("=" * 60)
    logger.info(f"扩展因子计算完成! 总耗时: {total_elapsed:.1f}s")
    logger.info(f"  总记录数: {total_records:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
