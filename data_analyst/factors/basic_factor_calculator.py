# -*- coding: utf-8 -*-
"""
基础因子计算模块 - 第一批因子

包含三类因子:
1. 动量因子: mom_20, mom_60, reversal_5
2. 量价因子: turnover, vol_ratio, price_vol_diverge
3. 波动率因子: volatility_20

运行: python data_analyst/factors/basic_factor_calculator.py
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import date, timedelta
from time import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, get_connection, execute_many

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
    """
    批量加载日K线数据

    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD

    Returns:
        dict: {stock_code: DataFrame}
    """
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

    # 转换数值类型
    for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'amount', 'turnover_rate']:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce')

    # 按股票分组
    result = {}
    codes = df_all['stock_code'].unique()

    for i, code in enumerate(codes):
        if (i + 1) % 500 == 0:
            logger.info(f"  加载数据: {i+1}/{len(codes)}")

        group = df_all[df_all['stock_code'] == code]
        sub = group.set_index('trade_date').sort_index()
        result[code] = sub

    logger.info(f"加载完成: {len(result)} 只股票")
    return result


# ============================================================
# 因子计算
# ============================================================

def calc_momentum_factors(df: pd.DataFrame) -> dict:
    """
    计算动量因子

    Args:
        df: 包含 close_price 列的 DataFrame

    Returns:
        dict: 因子值字典
    """
    close = df['close_price']

    # 20日收益率
    mom_20 = close.pct_change(20).iloc[-1]

    # 60日收益率
    mom_60 = close.pct_change(60).iloc[-1]

    # 5日反转 (负的5日收益率)
    reversal_5 = -close.pct_change(5).iloc[-1]

    return {
        'mom_20': float(mom_20) if not np.isnan(mom_20) else None,
        'mom_60': float(mom_60) if not np.isnan(mom_60) else None,
        'reversal_5': float(reversal_5) if not np.isnan(reversal_5) else None,
    }


def calc_volume_price_factors(df: pd.DataFrame) -> dict:
    """
    计算量价因子

    Args:
        df: 包含 close_price, volume, turnover_rate 列的 DataFrame

    Returns:
        dict: 因子值字典
    """
    volume = df['volume']
    close = df['close_price']

    # 换手率 (直接使用已有数据)
    turnover = df['turnover_rate'].iloc[-1] if 'turnover_rate' in df.columns else None

    # 量比 (今日量 vs 过去5日均量)
    vol_ma_5 = volume.rolling(5).mean()
    vol_ratio = volume.iloc[-1] / vol_ma_5.iloc[-1] if vol_ma_5.iloc[-1] > 0 else None

    # 价量背离: 涨价缩量 or 跌价放量
    price_change = close.pct_change().iloc[-1]
    vol_change = volume.pct_change().iloc[-1]
    # 正值表示价涨量缩(看空)，负值表示价跌量增(看空)
    if vol_change is not None and not np.isnan(vol_change):
        price_vol_diverge = price_change / (vol_change + 1e-10)
    else:
        price_vol_diverge = None

    return {
        'turnover': float(turnover) if turnover is not None and not np.isnan(turnover) else None,
        'vol_ratio': float(vol_ratio) if vol_ratio is not None and not np.isnan(vol_ratio) else None,
        'price_vol_diverge': float(price_vol_diverge) if price_vol_diverge is not None and not np.isnan(price_vol_diverge) else None,
    }


def calc_volatility_factors(df: pd.DataFrame) -> dict:
    """
    计算波动率因子

    Args:
        df: 包含 close_price 列的 DataFrame

    Returns:
        dict: 因子值字典
    """
    close = df['close_price']

    # 20日历史波动率 (日收益率的标准差)
    returns = close.pct_change()
    volatility_20 = returns.rolling(20).std().iloc[-1]

    return {
        'volatility_20': float(volatility_20) if not np.isnan(volatility_20) else None,
    }


def calc_all_basic_factors(df: pd.DataFrame) -> dict:
    """
    计算所有基础因子

    Args:
        df: 股票的日线数据 DataFrame

    Returns:
        dict: 所有因子值
    """
    if len(df) < 60:
        return None

    # 检查收盘价是否有效
    close = df['close_price'].iloc[-1]
    if close is None or close <= 0 or np.isnan(close):
        return None

    try:
        factors = {}
        factors.update(calc_momentum_factors(df))
        factors.update(calc_volume_price_factors(df))
        factors.update(calc_volatility_factors(df))
        factors['close'] = float(close)
        return factors
    except Exception as e:
        logger.debug(f"因子计算异常: {e}")
        return None


# ============================================================
# 批量计算
# ============================================================

def batch_calc_factors(all_data: dict) -> pd.DataFrame:
    """
    批量计算所有股票的因子

    Args:
        all_data: {stock_code: DataFrame}

    Returns:
        DataFrame: 因子矩阵
    """
    factor_dict = {}
    codes = list(all_data.keys())
    total = len(codes)

    for i, code in enumerate(codes):
        if (i + 1) % 500 == 0:
            logger.info(f"  计算因子: {i+1}/{total}")

        df = all_data[code]
        f = calc_all_basic_factors(df)
        if f is not None:
            factor_dict[code] = f

    logger.info(f"计算完成: {len(factor_dict)}/{total} 只股票有效")
    return pd.DataFrame(factor_dict).T


# ============================================================
# 数据库操作
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_basic_factor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    calc_date DATE NOT NULL COMMENT '计算日期',

    -- 动量因子
    mom_20 DOUBLE COMMENT '20日收益率',
    mom_60 DOUBLE COMMENT '60日收益率',
    reversal_5 DOUBLE COMMENT '5日反转因子',

    -- 量价因子
    turnover DOUBLE COMMENT '换手率(%)',
    vol_ratio DOUBLE COMMENT '量比',
    price_vol_diverge DOUBLE COMMENT '价量背离',

    -- 波动率因子
    volatility_20 DOUBLE COMMENT '20日历史波动率',

    -- 辅助字段
    close DOUBLE COMMENT '收盘价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_code_date (calc_date, stock_code),
    KEY idx_calc_date (calc_date),
    KEY idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票基础因子表';
"""


def create_factor_table():
    """创建因子表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("✅ 因子表创建成功: trade_stock_basic_factor")


def save_factors(factor_df: pd.DataFrame, calc_date) -> int:
    """
    保存因子到数据库

    Args:
        factor_df: 因子 DataFrame
        calc_date: 计算日期

    Returns:
        int: 保存的记录数
    """
    if isinstance(calc_date, str):
        calc_date = pd.to_datetime(calc_date).date()
    elif hasattr(calc_date, 'date'):
        calc_date = calc_date.date()

    factor_cols = ['mom_20', 'mom_60', 'reversal_5',
                   'turnover', 'vol_ratio', 'price_vol_diverge',
                   'volatility_20', 'close']

    conn = get_connection()
    cursor = conn.cursor()

    sql = f"""
        REPLACE INTO trade_stock_basic_factor
        (stock_code, calc_date, {', '.join(factor_cols)})
        VALUES (%s, %s, {', '.join(['%s'] * len(factor_cols))})
    """

    success_count = 0
    batch = []
    batch_size = 500

    for code, row in factor_df.iterrows():
        values = [code, calc_date] + [row.get(col, None) for col in factor_cols]
        batch.append(values)

        if len(batch) >= batch_size:
            try:
                cursor.executemany(sql, batch)
                conn.commit()
                success_count += len(batch)
            except Exception as e:
                logger.error(f"批量保存失败: {e}")
            batch = []

    # 保存剩余
    if batch:
        try:
            cursor.executemany(sql, batch)
            conn.commit()
            success_count += len(batch)
        except Exception as e:
            logger.error(f"保存失败: {e}")

    cursor.close()
    conn.close()

    return success_count


# ============================================================
# 主流程
# ============================================================

def calculate_and_save_factors(calc_date=None, start_date='2023-01-01'):
    """
    计算并保存因子

    Args:
        calc_date: 计算日期，默认今天
        start_date: K线数据起始日期
    """
    logger.info("=" * 60)
    logger.info("基础因子计算入库程序")
    logger.info("=" * 60)

    # 确保表存在
    logger.info("\n[1] 初始化因子表...")
    create_factor_table()

    # 设置日期
    if calc_date is None:
        calc_date = date.today()
    end_date = calc_date.strftime('%Y-%m-%d')

    # 加载数据
    logger.info(f"\n[2] 加载K线数据 ({start_date} ~ {end_date})...")
    t0 = time()
    all_data = load_daily_data(start_date, end_date)
    logger.info(f"  加载完成: {len(all_data)} 只股票, 耗时 {time()-t0:.1f}s")

    if not all_data:
        logger.error("  未加载到数据")
        return

    # 计算因子
    logger.info(f"\n[3] 计算基础因子...")
    t0 = time()
    factor_df = batch_calc_factors(all_data)
    logger.info(f"  计算完成: {len(factor_df)} 只股票, 耗时 {time()-t0:.1f}s")

    if factor_df.empty:
        logger.error("  因子计算失败")
        return

    # 显示因子统计
    logger.info(f"\n[4] 因子统计:")
    factor_cols = ['mom_20', 'mom_60', 'reversal_5', 'turnover', 'vol_ratio', 'price_vol_diverge', 'volatility_20']
    for col in factor_cols:
        if col in factor_df.columns:
            vals = factor_df[col].dropna()
            if len(vals) > 0:
                logger.info(f"  {col:<20} mean={vals.mean():>10.4f}  std={vals.std():>10.4f}  valid={len(vals)}")

    # 保存到数据库
    logger.info(f"\n[5] 保存到数据库 (calc_date={calc_date})...")
    t0 = time()
    count = save_factors(factor_df, calc_date)
    logger.info(f"  保存完成: {count} 条记录, 耗时 {time()-t0:.1f}s")

    # 验证数据
    logger.info(f"\n[6] 验证数据...")
    sql = "SELECT COUNT(*) as cnt FROM trade_stock_basic_factor WHERE calc_date = %s"
    result = execute_query(sql, [calc_date])
    saved_count = result[0]['cnt'] if result else 0
    logger.info(f"  数据库中 {calc_date} 的记录数: {saved_count}")

    # 显示前5条样例
    logger.info(f"\n[7] 因子样例 (前5只股票):")
    sample_sql = """
        SELECT stock_code, mom_20, mom_60, reversal_5, vol_ratio, volatility_20, close
        FROM trade_stock_basic_factor
        WHERE calc_date = %s
        LIMIT 5
    """
    samples = execute_query(sample_sql, [calc_date])
    if samples:
        header = f"  {'代码':<12} {'20日收益':>10} {'60日收益':>10} {'5日反转':>10} {'量比':>8} {'波动率':>10}"
        logger.info(header)
        logger.info(f"  {'-'*70}")
        for s in samples:
            mom_20_str = f"{s['mom_20']*100:.2f}%" if s['mom_20'] is not None else 'N/A'
            mom_60_str = f"{s['mom_60']*100:.2f}%" if s['mom_60'] is not None else 'N/A'
            rev_5_str = f"{s['reversal_5']*100:.2f}%" if s['reversal_5'] is not None else 'N/A'
            vol_ratio_str = f"{s['vol_ratio']:.2f}" if s['vol_ratio'] is not None else 'N/A'
            vol_20_str = f"{s['volatility_20']:.4f}" if s['volatility_20'] is not None else 'N/A'
            logger.info(f"  {s['stock_code']:<12} {mom_20_str:>10} {mom_60_str:>10} {rev_5_str:>10} {vol_ratio_str:>8} {vol_20_str:>10}")

    logger.info("\n" + "=" * 60)
    logger.info("✅ 基础因子计算入库完成!")
    logger.info("=" * 60)

    return factor_df


def backfill_factors(start_date='2024-01-01', end_date=None):
    """
    回填历史因子数据

    Args:
        start_date: 开始日期
        end_date: 结束日期，默认今天
    """
    if end_date is None:
        end_date = date.today()

    logger.info("=" * 60)
    logger.info("因子回填程序")
    logger.info(f"回填范围: {start_date} ~ {end_date}")
    logger.info("=" * 60)

    # 获取所有交易日
    sql = """
        SELECT DISTINCT trade_date
        FROM trade_stock_daily
        WHERE trade_date >= %s AND trade_date <= %s
        ORDER BY trade_date
    """
    rows = execute_query(sql, [start_date, end_date])
    trade_dates = [r['trade_date'] for r in rows]

    logger.info(f"共 {len(trade_dates)} 个交易日需要回填")

    # 逐日计算
    for i, td in enumerate(trade_dates):
        logger.info(f"\n[{i+1}/{len(trade_dates)}] 回填 {td}...")
        try:
            calculate_and_save_factors(calc_date=td, start_date='2023-01-01')
        except Exception as e:
            logger.error(f"  回填失败: {e}")
            continue

    logger.info("\n" + "=" * 60)
    logger.info("✅ 因子回填完成!")
    logger.info("=" * 60)


def main():
    """主函数"""
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
