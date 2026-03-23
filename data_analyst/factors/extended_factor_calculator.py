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
import pandas as pd
import numpy as np
from datetime import date, timedelta
from time import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, get_connection

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 配置
BATCH_SIZE = 500  # 每批处理的股票数量
START_DATE = '2024-01-01'
END_DATE = date.today().strftime('%Y-%m-%d')
DATA_START_DATE = '2023-01-01'  # 需要更早的数据来计算因子


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

    # 转换数值
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("✅ 扩展因子表创建成功: trade_stock_extended_factor")


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

    conn = get_connection()
    cursor = conn.cursor()

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
        cursor.close()
        conn.close()
        return 0

    # 分批插入
    batch_insert_size = 1000
    total_saved = 0
    for i in range(0, len(records), batch_insert_size):
        batch = records[i:i+batch_insert_size]
        try:
            cursor.executemany(sql, batch)
            conn.commit()
            total_saved += len(batch)
        except Exception as e:
            logger.error(f"保存失败: {e}")

    cursor.close()
    conn.close()

    return len(records)


def main():
    """主函数 - 按股票分批回填扩展因子"""
    logger.info("=" * 60)
    logger.info("扩展因子计算程序")
    logger.info(f"回填范围: {START_DATE} ~ {END_DATE}")
    logger.info(f"数据加载范围: {DATA_START_DATE} ~ {END_DATE}")
    logger.info("=" * 60)

    # 1. 创建表
    logger.info(f"\n[1] 初始化扩展因子表...")
    create_extended_factor_table()

    # 2. 获取所有股票代码
    logger.info(f"\n[2] 获取股票列表...")
    all_codes = get_all_stock_codes()
    total_stocks = len(all_codes)
    logger.info(f"  共 {total_stocks} 只股票")

    # 3. 加载财务数据 (一次性加载，避免重复查询)
    logger.info(f"\n[3] 加载财务数据...")
    t0 = time()
    all_financial_data = load_financial_data(all_codes)
    logger.info(f"  加载完成: {len(all_financial_data)} 只股票有财务数据, 耗时 {time()-t0:.1f}s")

    # 4. 分批处理
    logger.info(f"\n[4] 开始分批处理 (每批 {BATCH_SIZE} 只股票)...")
    total_records = 0
    total_time_start = time()

    for batch_idx in range(0, total_stocks, BATCH_SIZE):
        batch_codes = all_codes[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1
        total_batches = (total_stocks + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info(f"\n--- 批次 {batch_num}/{total_batches} ({len(batch_codes)} 只股票) ---")

        # 加载日线数据
        t0 = time()
        stock_data = load_stock_daily_data(batch_codes, DATA_START_DATE, END_DATE)
        logger.info(f"  日线数据加载完成: {len(stock_data)} 只股票, 耗时 {time()-t0:.1f}s")

        if not stock_data:
            continue

        # 计算因子
        t0 = time()
        factors_data = {}
        for code, df in stock_data.items():
            try:
                # 计算量价因子
                price_factors = calc_price_volume_factors(df)

                # 计算财务因子
                financial_df = all_financial_data.get(code)
                financial_factors = calc_financial_factors(df, financial_df) if financial_df is not None else None

                # 合并因子
                merged_factors = merge_and_prepare_factors(price_factors, financial_factors, code)

                if merged_factors is not None and not merged_factors.empty:
                    # 只保留目标日期范围内的因子
                    start_dt = pd.to_datetime(START_DATE)
                    end_dt = pd.to_datetime(END_DATE)
                    mask = (merged_factors.index >= start_dt) & (merged_factors.index <= end_dt)
                    filtered = merged_factors[mask]
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

        # 显示总进度
        elapsed = time() - total_time_start
        processed = min(batch_idx + BATCH_SIZE, total_stocks)
        speed = processed / elapsed if elapsed > 0 else 0
        eta = (total_stocks - processed) / speed / 60 if speed > 0 else 0

        logger.info(f"  >>> 总进度: {processed}/{total_stocks} 只股票 ({processed*100/total_stocks:.1f}%)")
        logger.info(f"  >>> 已保存: {total_records:,} 条记录")
        logger.info(f"  >>> 预计剩余时间: {eta:.1f} 分钟")

    # 5. 验证结果
    logger.info(f"\n[5] 验证结果...")
    sql = "SELECT COUNT(*) as cnt FROM trade_stock_extended_factor"
    result = execute_query(sql)
    total = result[0]['cnt'] if result else 0
    logger.info(f"  扩展因子表总记录数: {total:,}")

    sql = """
        SELECT calc_date, COUNT(*) as cnt
        FROM trade_stock_extended_factor
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
    logger.info(f"✅ 扩展因子计算完成!")
    logger.info(f"  总耗时: {total_elapsed/60:.1f} 分钟")
    logger.info(f"  总记录数: {total_records:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
