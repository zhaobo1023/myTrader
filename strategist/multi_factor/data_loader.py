# -*- coding: utf-8 -*-
"""
数据加载模块

从6张因子表加载并合并横截面数据:
- trade_stock_valuation_factor: pb, pe_ttm, market_cap
- trade_stock_basic_factor: volatility_20, close, mom_20, reversal_5
- trade_stock_extended_factor: roe_ttm, gross_margin, net_profit_growth, revenue_growth
- trade_stock_quality_factor: roa, debt_ratio
- trade_stock_daily_basic: dv_ttm
- trade_stock_daily: close_price (用于计算前瞻收益率 + ST过滤)

使用 pymysql + pd.read_sql 直接读取，支持大结果集。
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from config.db import get_connection

logger = logging.getLogger(__name__)


def _get_connection_long_timeout():
    """Get a connection with extended timeouts for large queries."""
    import time
    from config.db import DB_CONFIG
    import pymysql
    from pymysql.cursors import DictCursor

    cfg = dict(DB_CONFIG)
    cfg['read_timeout'] = 300
    cfg['write_timeout'] = 300
    cfg['connect_timeout'] = 30

    # retry up to 3 times with backoff
    for attempt in range(3):
        try:
            return pymysql.connect(**cfg)
        except Exception as e:
            wait = 5 * (attempt + 1)
            logger.warning(f"DB connect attempt {attempt+1} failed: {e}, retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Failed to connect to database after 3 attempts")


def _read_sql(sql: str, conn=None) -> pd.DataFrame:
    """Execute SQL and return DataFrame with extended timeout."""
    close_after = False
    if conn is None:
        conn = _get_connection_long_timeout()
        close_after = True
    try:
        df = pd.read_sql(sql, conn)
    finally:
        if close_after:
            conn.close()
    return df


def load_factor_panel(start_date: str, end_date: str) -> pd.DataFrame:
    """
    加载因子面板数据。

    Returns:
        DataFrame with MultiIndex (trade_date, stock_code), columns = factor names.
    """
    logger.info(f"Loading factor panel: {start_date} ~ {end_date}")

    # 复用同一个连接，避免反复建立连接
    conn = _get_connection_long_timeout()
    try:
        # 1) 估值因子: pb, pe_ttm, market_cap
        sql_val = f"""
            SELECT stock_code, calc_date AS trade_date,
                   pb, pe_ttm, market_cap
            FROM trade_stock_valuation_factor
            WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        """
        df_val = _read_sql(sql_val, conn)
        logger.info(f"  valuation_factor: {len(df_val):,} rows")

        # 2) 基础因子: volatility_20, close, mom_20, reversal_5
        sql_basic = f"""
            SELECT stock_code, calc_date AS trade_date,
                   volatility_20, close, mom_20, reversal_5
            FROM trade_stock_basic_factor
            WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        """
        df_basic = _read_sql(sql_basic, conn)
        logger.info(f"  basic_factor: {len(df_basic):,} rows")

        # 3) 扩展因子: roe_ttm, gross_margin, net_profit_growth, revenue_growth
        sql_ext = f"""
            SELECT stock_code, calc_date AS trade_date,
                   roe_ttm, gross_margin, net_profit_growth, revenue_growth
            FROM trade_stock_extended_factor
            WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        """
        df_ext = _read_sql(sql_ext, conn)
        logger.info(f"  extended_factor: {len(df_ext):,} rows")

        # 4) 质量因子: roa, debt_ratio
        sql_quality = f"""
            SELECT stock_code, calc_date AS trade_date,
                   roa, debt_ratio
            FROM trade_stock_quality_factor
            WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        """
        df_quality = _read_sql(sql_quality, conn)
        logger.info(f"  quality_factor: {len(df_quality):,} rows")

        # 5) 每日基本面: dv_ttm
        sql_daily_basic = f"""
            SELECT stock_code, trade_date,
                   dv_ttm
            FROM trade_stock_daily_basic
            WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}'
        """
        df_daily_basic = _read_sql(sql_daily_basic, conn)
        logger.info(f"  daily_basic: {len(df_daily_basic):,} rows")
    finally:
        conn.close()

    # 逐个 merge (outer join on date+code)
    dfs = [df_val, df_basic, df_ext, df_quality, df_daily_basic]
    dfs = [df for df in dfs if not df.empty]

    if not dfs:
        logger.error("No data loaded")
        return pd.DataFrame()

    for col in dfs[0].columns:
        if col not in ('stock_code', 'trade_date'):
            dfs[0][col] = pd.to_numeric(dfs[0][col], errors='coerce')

    df = dfs[0]
    for other in dfs[1:]:
        for col in other.columns:
            if col not in ('stock_code', 'trade_date'):
                other[col] = pd.to_numeric(other[col], errors='coerce')
        df = pd.merge(df, other, on=['trade_date', 'stock_code'], how='outer')

    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index(['trade_date', 'stock_code']).sort_index()
    logger.info(f"  merged panel: {len(df):,} rows, {len(df.columns)} cols")

    # 计算复合因子
    _add_composite_factors(df)

    return df


def _add_composite_factors(df: pd.DataFrame):
    """在面板上计算复合因子（如 pb_roe）。"""
    from .config import COMPOSITE_FACTORS

    for cf in COMPOSITE_FACTORS:
        name = cf['name']
        requires = cf['requires']
        formula = cf['formula']

        # 检查所需基础因子是否都存在
        missing = [r for r in requires if r not in df.columns]
        if missing:
            logger.warning(f"Composite factor {name}: missing columns {missing}, skipped")
            continue

        # pb_roe: roe_ttm / pb, 仅在 pb > 0 时有效
        if name == 'pb_roe':
            valid = df['pb'] > 0
            df.loc[valid, name] = df.loc[valid, 'roe_ttm'] / df.loc[valid, 'pb']
            # pb <= 0 或 roe 为空时设为 NaN
            df[name] = df[name].where(valid & df['roe_ttm'].notna())
            n_valid = df[name].notna().sum()
            logger.info(f"  composite factor {name}: {n_valid:,} valid values")


def load_forward_returns(start_date: str, end_date: str,
                         periods=(5, 10, 20)) -> pd.DataFrame:
    """
    计算前瞻收益率。

    Returns:
        DataFrame with MultiIndex (trade_date, stock_code),
        columns = forward_5d, forward_10d, forward_20d, ...
    """
    # 多拉一段数据用于计算尾部的前瞻收益
    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=45)
    end_ext = end_dt.strftime('%Y-%m-%d')

    sql = f"""
        SELECT stock_code, trade_date, close_price
        FROM trade_stock_daily
        WHERE trade_date >= '{start_date}' AND trade_date <= '{end_ext}'
        ORDER BY stock_code, trade_date
    """
    df = _read_sql(sql)
    if df.empty:
        logger.error("No daily price data for forward returns")
        return pd.DataFrame()

    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')

    results = []
    for code, group in df.groupby('stock_code'):
        group = group.sort_values('trade_date').set_index('trade_date')
        for p in periods:
            group[f'forward_{p}d'] = group['close_price'].shift(-p) / group['close_price'] - 1
        results.append(group)

    result = pd.concat(results)
    result = result.reset_index().set_index(['trade_date', 'stock_code'])
    # 只保留原始日期范围内的数据
    mask = result.index.get_level_values('trade_date') <= pd.Timestamp(end_date)
    result = result[mask]

    logger.info(f"Forward returns: {len(result):,} rows, periods={periods}")
    return result
