# -*- coding: utf-8 -*-
"""
Hard-tech data loader

Loads and merges factor data from multiple tables:
  - trade_stock_hardtech_factor (rd_intensity, rd_growth, rd_efficiency, gross_margin_trend)
  - trade_stock_extended_factor (revenue_growth, gross_margin, roe_ttm)
  - trade_stock_basic_factor (mom_20)
  - trade_stock_valuation_factor (market_cap)
  - trade_stock_daily (close_price for forward returns)
"""
import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from config.db import get_connection, execute_query

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50000
MAX_RETRIES = 3
RETRY_BACKOFF = 10


def _read_sql_by_batches(sql_template, batch_col, batch_values):
    """Read SQL by date batches with retry."""
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


def load_hardtech_panel(start_date, end_date):
    """
    Load hard-tech factor panel data.

    Returns:
        DataFrame with MultiIndex (trade_date, stock_code), columns = factor names.
    """
    logger.info(f"Loading hard-tech factor panel: {start_date} ~ {end_date}")

    # Get available dates from hardtech_factor table
    conn = get_connection()
    try:
        dates_sql = f"""
            SELECT DISTINCT calc_date FROM trade_stock_hardtech_factor
            WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
            ORDER BY calc_date
        """
        dates_df = pd.read_sql(dates_sql, conn)
    finally:
        conn.close()

    if dates_df.empty:
        # Fallback to valuation_factor dates
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
        logger.error("No dates found")
        return pd.DataFrame()

    dates = [str(d) for d in dates_df.iloc[:, 0]]
    logger.info(f"  {len(dates)} trading dates to process")

    # Sample monthly for performance (hardtech factors change slowly)
    sampled = dates[::20]
    if dates[-1] not in sampled:
        sampled.append(dates[-1])
    logger.info(f"  Sampled {len(sampled)} monthly dates")

    # 1) Hard-tech factors
    sql_hardtech_tpl = """
        SELECT stock_code, calc_date AS trade_date,
               rd_intensity, rd_growth, rd_efficiency, gross_margin_trend
        FROM trade_stock_hardtech_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading hardtech_factor...")
    df_hardtech = _read_sql_by_batches(sql_hardtech_tpl, 'trade_date', sampled)

    if df_hardtech.empty:
        logger.warning("No hardtech factor data found")
        return pd.DataFrame()

    # 2) Extended factors: revenue_growth, gross_margin, roe_ttm
    sql_ext_tpl = """
        SELECT stock_code, calc_date AS trade_date,
               revenue_growth, gross_margin, roe_ttm
        FROM trade_stock_extended_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading extended_factor...")
    df_ext = _read_sql_by_batches(sql_ext_tpl, 'trade_date', sampled)

    # 3) Basic factors: mom_20
    sql_basic_tpl = """
        SELECT stock_code, calc_date AS trade_date,
               mom_20
        FROM trade_stock_basic_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading basic_factor...")
    df_basic = _read_sql_by_batches(sql_basic_tpl, 'trade_date', sampled)

    # 4) Valuation factors: market_cap
    sql_val_tpl = """
        SELECT stock_code, calc_date AS trade_date,
               market_cap
        FROM trade_stock_valuation_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading valuation_factor...")
    df_val = _read_sql_by_batches(sql_val_tpl, 'trade_date', sampled)

    # Merge all
    dfs = [df_hardtech, df_ext, df_basic, df_val]
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

    # Log data coverage
    for col in result.columns:
        coverage = result[col].notna().mean()
        logger.info(f"    {col}: {coverage:.1%} coverage")

    return result


def load_forward_returns(start_date, end_date, periods=(20,)):
    """Calculate forward returns for IC evaluation."""
    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=45)
    end_ext = end_dt.strftime('%Y-%m-%d')

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

    # Sample monthly to match panel dates
    sampled = dates[::20]
    if dates[-1] not in sampled:
        sampled.append(dates[-1])

    # Need all daily prices between sampled dates for forward return calc
    # Load full range
    sql_tpl = """
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

    # Calculate forward returns
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

    logger.info(f"  Forward returns: {len(result):,} rows")
    return result
