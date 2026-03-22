# -*- coding: utf-8 -*-
"""
因子计算模块

使用 TA-Lib 计算技术因子:
  - momentum_20d: 20日动量 (ROC)
  - momentum_60d: 60日动量 (ROC)
  - volatility: 波动率 (ATR/Close)
  - rsi_14: RSI(14)
  - adx_14: ADX(14) 趋势强度
  - turnover_ratio: 换手率 (当日量/20日均量)
  - price_position: 价格位置 (60日区间内位置)
  - macd_signal: MACD柱状图

运行: python data_analyst/factors/factor_calculator.py
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
from config.settings import settings
from data_analyst.factors.factor_storage import (
    create_factor_table, batch_save_factors,
    load_factors, get_factor_dates, get_latest_factor_date
)

# 尝试导入 TA-Lib
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
    logging.warning("TA-Lib 未安装，因子计算功能将不可用")


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# 因子配置
# ============================================================

FACTOR_CONFIG = {
    'momentum_20d': {'name': '20日动量', 'direction': 1, 'weight': 0.20},
    'momentum_60d': {'name': '60日动量', 'direction': 1, 'weight': 0.15},
    'volatility': {'name': '波动率', 'direction': -1, 'weight': 0.15},
    'rsi_14': {'name': 'RSI(14)', 'direction': -1, 'weight': 0.10},
    'adx_14': {'name': 'ADX(14)', 'direction': 1, 'weight': 0.10},
    'turnover_ratio': {'name': '换手率', 'direction': 1, 'weight': 0.10},
    'price_position': {'name': '价格位置', 'direction': -1, 'weight': 0.10},
    'macd_signal': {'name': 'MACD信号', 'direction': 1, 'weight': 0.10},
}


# ============================================================
# 因子计算
# ============================================================

def calc_all_factors(df):
    """
    计算单只股票的全部因子

    Args:
        df: DataFrame, 包含 open, high, low, close, volume 列

    Returns:
        dict: 因子字典， 或 None
    """
    if not HAS_TALIB:
        logger.error("TA-Lib 未安装，无法计算因子")
        return None

    if len(df) < 60:
        return None

    h = df['high'].values.astype(np.float64)
    l = df['low'].values.astype(np.float64)
    c = df['close'].values.astype(np.float64)
    v = df['volume'].values.astype(np.float64)

    if c[-1] <= 0 or np.isnan(c[-1]):
        return None

    try:
        # 使用 TA-Lib 计算
        roc_20 = talib.ROC(c, timeperiod=20)
        roc_60 = talib.ROC(c, timeperiod=60)
        atr = talib.ATR(h, l, c, timeperiod=14)
        rsi = talib.RSI(c, timeperiod=14)
        adx = talib.ADX(h, l, c, timeperiod=14)
        vol_ma = talib.SMA(v, timeperiod=20)
        macd_line, macd_signal, macd_hist = talib.MACD(c)

        # 60日最高/最低价
        high_60 = np.nanmax(h[-60:])
        low_60 = np.nanmin(l[-60:])
        price_range = high_60 - low_60

        vol_ma_val = vol_ma[-1] if not np.isnan(vol_ma[-1]) and vol_ma[-1] > 0 else 1

        factors = {
            'momentum_20d': float(roc_20[-1]) if not np.isnan(roc_20[-1]) else 0,
            'momentum_60d': float(roc_60[-1]) if not np.isnan(roc_60[-1]) else 0,
            'volatility': float(atr[-1] / c[-1]) if not np.isnan(atr[-1]) and c[-1] > 0 else 0,
            'rsi_14': float(rsi[-1]) if not np.isnan(rsi[-1]) else 50,
            'adx_14': float(adx[-1]) if not np.isnan(adx[-1]) else 0,
            'turnover_ratio': float(v[-1] / vol_ma_val) if vol_ma_val > 0 else 1,
            'price_position': float((c[-1] - low_60) / price_range) if price_range > 0 else 0.5,
            'macd_signal': float(macd_hist[-1]) if not np.isnan(macd_hist[-1]) else 0,
            'close': float(c[-1]),
        }
        return factors
    except Exception as e:
        logger.error(f"因子计算失败: {e}")
        return None


def batch_load_daily(start_date, end_date, min_bars=60):
    """批量加载日K线数据"""
    sql = """
        select stock_code, trade_date, open_price, high_price, low_price, close_price, volume
        from trade_stock_daily
        where trade_date >= %s and trade_date <= %s
        order by stock_code, trade_date asc
    """
    rows = execute_query(sql, [start_date, end_date])
    if not rows:
        return {}

    df_all = pd.DataFrame(rows)
    df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
    for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume']:
        df_all[col] = pd.to_numeric(df_all[col], errors='coerce')

    result = {}
    codes = df_all['stock_code'].unique()

    for code in codes:
        group = df_all[df_all['stock_code'] == code]
        sub = group.set_index('trade_date').sort_index()
        sub = sub[['open_price', 'high_price', 'low_price', 'close_price', 'volume']]
        sub.columns = ['open', 'high', 'low', 'close', 'volume']
        if len(sub) >= min_bars:
            result[code] = sub

    return result


def batch_calc_factors(all_data):
    """批量计算所有股票的因子"""
    factor_dict = {}
    codes = list(all_data.keys())
    total = len(codes)

    for i, code in enumerate(codes):
        if (i + 1) % 100 == 0:
            logger.info(f"计算因子: {i+1}/{total}")
        df = all_data[code]
        f = calc_all_factors(df)
        if f is not None:
            factor_dict[code] = f

    return pd.DataFrame(factor_dict).T


# ============================================================
# 主流程
# ============================================================

def calculate_factors_for_date(calc_date=None, start_date='2024-01-01'):
    """
    计算指定日期的因子

    Args:
        calc_date: 计算日期， 默认今天
        start_date: K线数据起始日期
    """
    if not HAS_TALIB:
        logger.error("TA-Lib 未安装，无法计算因子")
        return

    # 确保表存在
    logger.info("初始化因子表...")
    create_factor_table()

    # 设置日期
    if calc_date is None:
        calc_date = date.today()
    end_date = calc_date.strftime('%Y-%m-%d')

    # 检查是否已有当天数据
    logger.info("检查已有数据...")
    latest = get_latest_factor_date()
    logger.info(f"最新因子日期: {latest or '无'}")
    if latest == calc_date:
        logger.warning(f"{calc_date} 的因子数据已存在，将覆盖更新")

    # 加载数据
    logger.info(f"加载K线数据 ({start_date} ~ {end_date})...")
    t0 = time()
    all_data = batch_load_daily(start_date, end_date)
    logger.info(f"加载完成: {len(all_data)} 只股票, 耗时 {time()-t0:.1f}s")

    if not all_data:
        logger.error("未加载到数据")
        return

    # 计算因子
    logger.info("计算技术因子...")
    t0 = time()
    factor_df = batch_calc_factors(all_data)
    logger.info(f"计算完成: {len(factor_df)} 只股票, 耗时 {time()-t0:.1f}s")

    if factor_df.empty:
        logger.error("因子计算失败")
        return

    # 显示因子统计
    logger.info("因子统计:")
    factor_cols = ['momentum_20d', 'momentum_60d', 'volatility', 'rsi_14',
                   'adx_14', 'turnover_ratio', 'price_position', 'macd_signal']
    for col in factor_cols:
        if col in factor_df.columns:
            vals = factor_df[col].dropna()
            logger.info(f"  {col:<16} mean={vals.mean():>8.3f}  std={vals.std():>8.3f}")

    # 保存到数据库
    logger.info(f"保存到数据库 (calc_date={calc_date})...")
    t0 = time()
    count = batch_save_factors(factor_df, calc_date)
    logger.info(f"保存完成: {count} 条记录, 耗时 {time()-t0:.1f}s")

    # 验证数据
    logger.info("验证数据...")
    saved_df = load_factors(calc_date)
    if len(saved_df) == len(factor_df):
        logger.info(f"✅ 数据验证通过: {len(saved_df)} 条记录")

        # 显示前5条
        logger.info("前5只股票因子:")
        logger.info(f"  {'代码':<14} {'20D动量':>10} {'RSI':>8} {'波动率':>10} {'收盘价':>10}")
        logger.info(f"  {'-'*56}")
        for i, (code, row) in enumerate(saved_df.head(5).iterrows()):
            logger.info(f"  {code:<14} {row.get('momentum_20d', 0):>+9.2f}% "
                          f"{row.get('rsi_14', 0):>8.1f} {row.get('volatility', 0):>10.4f} "
                          f"{row.get('close', 0):>10.2f}")
    else:
        logger.error(f"数据验证失败: 保存{len(factor_df)}条, 读取{len(saved_df)}条")

    # 显示所有因子日期
    logger.info("因子数据汇总:")
    dates = get_factor_dates()
    for d in dates:
        logger.info(f"  {d['calc_date']}: {d['stock_count']} 只股票")

    logger.info("=" * 60)
    logger.info("✅ 因子计算完成!")
    logger.info("=" * 60)


    return factor_df


def main():
    """主函数 - 因子计算入库"""
    print("=" * 60)
    print("因子计算入库程序")
    print("=" * 60)

    calculate_factors_for_date()


if __name__ == "__main__":
    main()
