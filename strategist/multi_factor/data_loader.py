# -*- coding: utf-8 -*-
"""
数据加载模块

从因子表加载并合并横截面数据。使用分批读取 + 重试机制应对线上 DB 网络不稳定。
"""

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from config.db import get_connection, execute_query

logger = logging.getLogger(__name__)

# 分批读取参数
CHUNK_SIZE = 50000
MAX_RETRIES = 3
RETRY_BACKOFF = 10  # seconds


def _read_sql_chunked(sql: str, batch_col: str = None, batch_values: list = None) -> pd.DataFrame:
    """
    分批读取 SQL，避免大结果集导致网络超时。

    Args:
        sql: SQL with placeholder for batch filter
        batch_col: column name to partition by (e.g. 'trade_date')
        batch_values: ordered list of values to iterate over
    """
    if batch_col and batch_values:
        return _read_sql_by_batches(sql, batch_col, batch_values)
    else:
        return _read_sql_with_retry(sql)


def _read_sql_with_retry(sql: str) -> pd.DataFrame:
    """Read SQL with retry on connection loss."""
    for attempt in range(MAX_RETRIES):
        try:
            from config.db import get_connection
            conn = get_connection()
            try:
                df = pd.read_sql(sql, conn)
            finally:
                conn.close()
            return df
        except Exception as e:
            wait = RETRY_BACKOFF * (attempt + 1)
            logger.warning(f"SQL read attempt {attempt+1}/{MAX_RETRIES} failed: {e}, retry in {wait}s")
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)
            else:
                raise


def _read_sql_by_batches(sql_template: str, batch_col: str, batch_values: list) -> pd.DataFrame:
    """
    按日期分批读取，每批独立连接，避免长连接断开。
    """
    from config.db import get_connection

    all_dfs = []
    total = len(batch_values)

    for i, val in enumerate(batch_values):
        for attempt in range(MAX_RETRIES):
            try:
                conn = get_connection()
                try:
                    sql = sql_template.replace(f'__{batch_col}__', str(val))
                    df = pd.read_sql(sql, conn)
                finally:
                    conn.close()
                if not df.empty:
                    all_dfs.append(df)
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF)
                    continue
                logger.error(f"Failed to read batch {batch_col}={val}: {e}")
                break

        if (i + 1) % 20 == 0 or i == total - 1:
            logger.info(f"  batch progress: {i+1}/{total} ({batch_col})")

    if not all_dfs:
        return pd.DataFrame()

    result = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"  total rows: {len(result):,}")
    return result


def load_factor_panel(start_date: str, end_date: str) -> pd.DataFrame:
    """
    加载因子面板数据。按日期分批读取，避免网络超时。

    Returns:
        DataFrame with MultiIndex (trade_date, stock_code), columns = factor names.
    """
    logger.info(f"Loading factor panel: {start_date} ~ {end_date}")

    # 先获取日期列表
    from config.db import get_connection
    conn = get_connection()
    try:
        dates_sql = f"""
            SELECT DISTINCT calc_date FROM trade_stock_valuation_factor
            WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
            ORDER BY calc_date
        """
        dates_df = pd.read_sql(dates_sql, conn)
    finally:
        conn.close()

    if dates_df.empty:
        logger.error("No dates found in valuation_factor")
        return pd.DataFrame()

    dates = [str(d) for d in dates_df.iloc[:, 0]]
    logger.info(f"  {len(dates)} trading dates to process")

    # 1) 估值因子: pb, pe_ttm, market_cap
    sql_val_tpl = f"""
        SELECT stock_code, calc_date AS trade_date,
               pb, pe_ttm, market_cap
        FROM trade_stock_valuation_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading valuation_factor...")
    df_val = _read_sql_by_batches(sql_val_tpl, 'trade_date', dates)

    # 2) 基础因子: volatility_20, close
    sql_basic_tpl = f"""
        SELECT stock_code, calc_date AS trade_date,
               volatility_20, close
        FROM trade_stock_basic_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading basic_factor...")
    df_basic = _read_sql_by_batches(sql_basic_tpl, 'trade_date', dates)

    # 3) 扩展因子: roe_ttm
    sql_ext_tpl = f"""
        SELECT stock_code, calc_date AS trade_date,
               roe_ttm
        FROM trade_stock_extended_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading extended_factor...")
    df_ext = _read_sql_by_batches(sql_ext_tpl, 'trade_date', dates)

    # merge
    dfs = [df_val, df_basic, df_ext]
    dfs = [df for df in dfs if not df.empty]

    if not dfs:
        logger.error("No data loaded")
        return pd.DataFrame()

    for df in dfs:
        for col in df.columns:
            if col not in ('stock_code', 'trade_date'):
                df[col] = pd.to_numeric(df[col], errors='coerce')

    result = dfs[0]
    for other in dfs[1:]:
        result = pd.merge(result, other, on=['trade_date', 'stock_code'], how='outer')

    result['trade_date'] = pd.to_datetime(result['trade_date'])
    result = result.set_index(['trade_date', 'stock_code']).sort_index()
    logger.info(f"  merged panel: {len(result):,} rows, {len(result.columns)} cols")

    # 计算复合因子
    _add_composite_factors(result)

    return result


def load_forward_returns(start_date: str, end_date: str,
                         periods=(5, 10, 20)) -> pd.DataFrame:
    """
    计算前瞻收益率。按日期分批读取。
    """
    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=45)
    end_ext = end_dt.strftime('%Y-%m-%d')

    # 获取日期列表
    from config.db import get_connection
    conn = get_connection()
    try:
        dates_sql = f"""
            SELECT DISTINCT trade_date FROM trade_stock_daily
            WHERE trade_date >= '{start_date}' AND trade_date <= '{end_ext}'
            ORDER BY trade_date
        """
        dates_df = pd.read_sql(dates_sql, conn)
    finally:
        conn.close()

    if dates_df.empty:
        return pd.DataFrame()

    dates = [str(d) for d in dates_df.iloc[:, 0]]

    # 按日分批读取价格数据
    sql_tpl = f"""
        SELECT stock_code, trade_date, close_price
        FROM trade_stock_daily
        WHERE trade_date = '__trade_date__'
    """
    logger.info(f"  Loading daily prices ({len(dates)} dates)...")
    df_all = _read_sql_by_batches(sql_tpl, 'trade_date', dates)

    if df_all.empty:
        return pd.DataFrame()

    df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
    df_all['close_price'] = pd.to_numeric(df_all['close_price'], errors='coerce')

    # 计算前瞻收益率
    results = []
    for code, group in df_all.groupby('stock_code'):
        group = group.sort_values('trade_date').set_index('trade_date')
        for p in periods:
            group[f'forward_{p}d'] = group['close_price'].shift(-p) / group['close_price'] - 1
        results.append(group)

    result = pd.concat(results)
    result = result.reset_index().set_index(['trade_date', 'stock_code'])
    mask = result.index.get_level_values('trade_date') <= pd.Timestamp(end_date)
    result = result[mask]

    logger.info(f"  Forward returns: {len(result):,} rows, periods={periods}")
    return result


def _add_composite_factors(df: pd.DataFrame):
    """在面板上计算复合因子（如 pb_roe）。"""
    from .config import COMPOSITE_FACTORS

    for cf in COMPOSITE_FACTORS:
        name = cf['name']
        requires = cf['requires']

        missing = [r for r in requires if r not in df.columns]
        if missing:
            logger.warning(f"Composite factor {name}: missing columns {missing}, skipped")
            continue

        if name == 'pb_roe':
            valid = (df['pb'] > 0) & df['roe_ttm'].notna()
            df.loc[valid, name] = df.loc[valid, 'roe_ttm'] / df.loc[valid, 'pb']
            df[name] = df[name].where(valid)
            n_valid = df[name].notna().sum()
            logger.info(f"  composite factor {name}: {n_valid:,} valid values")


def load_stock_filter() -> set:
    """
    加载股票过滤黑名单。

    Returns:
        set of stock_code to exclude
    """
    from .config import FILTER_EXCLUDE_ST, FILTER_MIN_LIST_DAYS, FILTER_EXCLUDE_KCBJ

    blacklist = set()
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 1. ST stocks
        if FILTER_EXCLUDE_ST:
            cursor.execute(
                "SELECT stock_code FROM trade_stock_basic WHERE is_st = 1"
            )
            st_codes = {row[0] for row in cursor.fetchall()}
            blacklist.update(st_codes)
            logger.info(f"  filter: {len(st_codes)} ST stocks excluded")

        # 2. Newly listed stocks (approximate by MIN trade_date)
        if FILTER_MIN_LIST_DAYS > 0:
            cutoff = (pd.Timestamp.now() - pd.Timedelta(days=int(FILTER_MIN_LIST_DAYS * 365 / 250)))
            cursor.execute(
                f"SELECT stock_code FROM trade_stock_daily "
                f"GROUP BY stock_code HAVING MIN(trade_date) > '{cutoff.strftime('%Y-%m-%d')}'"
            )
            new_codes = {row[0] for row in cursor.fetchall()}
            blacklist.update(new_codes)
            logger.info(f"  filter: {len(new_codes)} newly listed stocks excluded "
                        f"(<{FILTER_MIN_LIST_DAYS} trading days)")

        # 3. ChiNext (300)科创板(688)北交所(8/4) - optional
        if FILTER_EXCLUDE_KCBJ:
            cursor.execute(
                "SELECT stock_code FROM trade_stock_basic "
                "WHERE stock_code LIKE '688%' OR stock_code LIKE '8%' OR stock_code LIKE '4%'"
            )
            kcbj_codes = {row[0] for row in cursor.fetchall()}
            blacklist.update(kcbj_codes)
            logger.info(f"  filter: {len(kcbj_codes)} KCB/BJ stocks excluded")

    finally:
        conn.close()

    logger.info(f"  filter: total blacklist = {len(blacklist)} stocks")
    return blacklist
