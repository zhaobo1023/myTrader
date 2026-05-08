# -*- coding: utf-8 -*-
"""
Hard-tech data loader

Loads and merges factor data from multiple tables:
  - trade_stock_hardtech_factor (rd_intensity, rd_growth, rd_efficiency, gross_margin_trend)
  - trade_stock_extended_factor (revenue_growth, gross_margin, net_profit_growth)
  - trade_stock_basic_factor (mom_20)
  - trade_stock_rps (rps_250)
  - trade_stock_valuation_factor (pe_ttm)
  - trade_stock_daily (close_price for forward returns)
"""
import logging
import time
from datetime import datetime
from datetime import timedelta

import pandas as pd

from config.db import get_connection

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = 10

# Authoritative industry list (must match hardtech_factor_calculator.HARD_TECH_INDUSTRIES)
HARD_TECH_INDUSTRIES = [
    '电子', '计算机', '通信', '电力设备',
    '机械设备', '国防军工', '医药生物', '汽车',
    '有色金属', '化工',
]


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

    # Get available dates from hardtech_factor table (parameterized)
    conn = get_connection()
    try:
        dates_sql = """
            SELECT DISTINCT calc_date FROM trade_stock_hardtech_factor
            WHERE calc_date >= %s AND calc_date <= %s
            ORDER BY calc_date
        """
        dates_df = pd.read_sql(dates_sql, conn, params=(start_date, end_date))
    finally:
        conn.close()

    if dates_df.empty:
        # Fallback to valuation_factor dates (parameterized)
        conn = get_connection()
        try:
            dates_sql = """
                SELECT DISTINCT calc_date FROM trade_stock_valuation_factor
                WHERE calc_date >= %s AND calc_date <= %s
                ORDER BY calc_date
            """
            dates_df = pd.read_sql(dates_sql, conn, params=(start_date, end_date))
        finally:
            conn.close()

    if dates_df.empty:
        logger.error("No dates found")
        return pd.DataFrame()

    dates = [str(d) for d in dates_df.iloc[:, 0]]
    logger.info(f"  {len(dates)} trading dates to process")

    # Sample every 20 trading days for performance (hardtech factors change slowly)
    sampled = dates[::20]
    if dates[-1] not in sampled:
        sampled.append(dates[-1])
    logger.info(f"  Sampled {len(sampled)} dates")

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

    # 2) Extended factors: revenue_growth, gross_margin, net_profit_growth
    sql_ext_tpl = """
        SELECT stock_code, calc_date AS trade_date,
               revenue_growth, gross_margin, net_profit_growth
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

    # 4) RPS: rps_250 (uses trade_date, not calc_date)
    sql_rps_tpl = """
        SELECT stock_code, trade_date,
               rps_250
        FROM trade_stock_rps
        WHERE trade_date = '__trade_date__'
    """
    logger.info("  Loading rps...")
    df_rps = _read_sql_by_batches(sql_rps_tpl, 'trade_date', sampled)

    # 5) Valuation factors: pe_ttm
    sql_val_tpl = """
        SELECT stock_code, calc_date AS trade_date,
               pe_ttm
        FROM trade_stock_valuation_factor
        WHERE calc_date = '__trade_date__'
    """
    logger.info("  Loading valuation_factor...")
    df_val = _read_sql_by_batches(sql_val_tpl, 'trade_date', sampled)

    # Merge all
    dfs = [df_hardtech, df_ext, df_basic, df_rps, df_val]
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
        dates_sql = """
            SELECT DISTINCT trade_date FROM trade_stock_daily
            WHERE trade_date >= %s AND trade_date <= %s
            ORDER BY trade_date
        """
        dates_df = pd.read_sql(dates_sql, conn, params=(start_date, end_ext))
    finally:
        conn.close()

    if dates_df.empty:
        return pd.DataFrame()

    dates = [str(d) for d in dates_df.iloc[:, 0]]

    # Load full daily prices for forward return calculation
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


def load_single_day_factors(trade_date, stock_codes=None, env='online'):
    """
    Load factor values for a single trade date.

    Args:
        trade_date: str, date string YYYY-MM-DD
        stock_codes: optional list of stock codes to filter
        env: database environment

    Returns:
        DataFrame with index=stock_code, columns=factor names
    """
    if env == 'online':
        from config.db import get_online_connection
        conn_fn = get_online_connection
    else:
        conn_fn = get_connection

    dfs = []

    # 1) Hard-tech factors
    sql = """
        SELECT stock_code, calc_date,
               rd_intensity, rd_growth, rd_efficiency, gross_margin_trend
        FROM trade_stock_hardtech_factor
        WHERE calc_date = %s
    """
    if stock_codes:
        placeholders = ','.join(['%s'] * len(stock_codes))
        sql += f" AND stock_code IN ({placeholders})"
        params = [trade_date] + stock_codes
    else:
        params = [trade_date]

    try:
        conn = conn_fn()
        try:
            df = pd.read_sql(sql, conn, params=params)
        finally:
            conn.close()
        if not df.empty:
            df = df.rename(columns={'calc_date': 'trade_date'})
            dfs.append(df)
    except Exception as e:
        logger.warning(f"Failed to load hardtech factors for {trade_date}: {e}")

    # 2) Extended factors
    sql_ext = """
        SELECT stock_code, calc_date,
               revenue_growth, gross_margin, net_profit_growth
        FROM trade_stock_extended_factor
        WHERE calc_date = %s
    """
    if stock_codes:
        sql_ext += f" AND stock_code IN ({placeholders})"
        params_ext = [trade_date] + stock_codes
    else:
        params_ext = [trade_date]

    try:
        conn = conn_fn()
        try:
            df_ext = pd.read_sql(sql_ext, conn, params=params_ext)
        finally:
            conn.close()
        if not df_ext.empty:
            df_ext = df_ext.rename(columns={'calc_date': 'trade_date'})
            dfs.append(df_ext)
    except Exception as e:
        logger.warning(f"Failed to load extended factors for {trade_date}: {e}")

    # 3) Basic factors: mom_20
    sql_basic = """
        SELECT stock_code, calc_date, mom_20
        FROM trade_stock_basic_factor
        WHERE calc_date = %s
    """
    if stock_codes:
        sql_basic += f" AND stock_code IN ({placeholders})"
        params_basic = [trade_date] + stock_codes
    else:
        params_basic = [trade_date]

    try:
        conn = conn_fn()
        try:
            df_basic = pd.read_sql(sql_basic, conn, params=params_basic)
        finally:
            conn.close()
        if not df_basic.empty:
            df_basic = df_basic.rename(columns={'calc_date': 'trade_date'})
            dfs.append(df_basic)
    except Exception as e:
        logger.warning(f"Failed to load basic factors for {trade_date}: {e}")

    # 4) RPS: rps_250 (uses trade_date, not calc_date)
    sql_rps = """
        SELECT stock_code, trade_date, rps_250
        FROM trade_stock_rps
        WHERE trade_date = %s
    """
    if stock_codes:
        sql_rps += f" AND stock_code IN ({placeholders})"
        params_rps = [trade_date] + stock_codes
    else:
        params_rps = [trade_date]

    try:
        conn = conn_fn()
        try:
            df_rps = pd.read_sql(sql_rps, conn, params=params_rps)
        finally:
            conn.close()
        if not df_rps.empty:
            df_rps = df_rps.rename(columns={'calc_date': 'trade_date'})
            dfs.append(df_rps)
    except Exception as e:
        logger.warning(f"Failed to load rps for {trade_date}: {e}")

    # 5) Valuation: pe_ttm
    sql_val = """
        SELECT stock_code, calc_date, pe_ttm
        FROM trade_stock_valuation_factor
        WHERE calc_date = %s
    """
    if stock_codes:
        sql_val += f" AND stock_code IN ({placeholders})"
        params_val = [trade_date] + stock_codes
    else:
        params_val = [trade_date]

    try:
        conn = conn_fn()
        try:
            df_val = pd.read_sql(sql_val, conn, params=params_val)
        finally:
            conn.close()
        if not df_val.empty:
            df_val = df_val.rename(columns={'calc_date': 'trade_date'})
            dfs.append(df_val)
    except Exception as e:
        logger.warning(f"Failed to load valuation factors for {trade_date}: {e}")

    if not dfs:
        return pd.DataFrame()

    # Merge
    result = dfs[0]
    for other in dfs[1:]:
        result = pd.merge(result, other, on=['trade_date', 'stock_code'], how='outer')

    for col in result.columns:
        if col not in ('stock_code', 'trade_date'):
            result[col] = pd.to_numeric(result[col], errors='coerce')

    result = result.set_index('stock_code')
    logger.info(f"Single day factors for {trade_date}: {len(result)} stocks")
    return result


def load_hardtech_universe(env='online'):
    """
    Load hard-tech stock universe from trade_stock_basic.

    Filters by sw_level1 industry (same list as hardtech_factor_calculator)
    and excludes ST stocks.

    Returns:
        DataFrame with columns [stock_code, stock_name, sw_industry]
    """
    if env == 'online':
        from config.db import get_online_connection
        conn_fn = get_online_connection
    else:
        conn_fn = get_connection

    placeholders = ','.join(['%s'] * len(HARD_TECH_INDUSTRIES))
    sql = f"""
        SELECT b.stock_code, b.stock_name, b.industry AS sw_industry
        FROM trade_stock_basic b
        WHERE b.industry IN ({placeholders})
          AND b.stock_name NOT LIKE '%%ST%%'
    """
    params = HARD_TECH_INDUSTRIES

    df = pd.DataFrame()
    try:
        conn = conn_fn()
        try:
            df = pd.read_sql(sql, conn, params=params)
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Failed to load from trade_stock_basic: {e}")

    # Fallback: use trade_stock_info when trade_stock_basic has no industry data
    if df.empty:
        logger.info("No results from trade_stock_basic, trying trade_stock_info fallback")
        try:
            conn = conn_fn()
            try:
                sql2 = """
                    SELECT i.stock_code, i.stock_name,
                           CASE WHEN i.industry LIKE '%%软件%%' THEN '计算机'
                                WHEN i.industry LIKE '%%通信%%' THEN '通信'
                                WHEN i.industry LIKE '%%电子%%' THEN '电子'
                                WHEN i.industry LIKE '%%医药%%' THEN '医药生物'
                                WHEN i.industry LIKE '%%汽车%%' THEN '汽车'
                                WHEN i.industry LIKE '%%机械%%' THEN '机械设备'
                                WHEN i.industry LIKE '%%化学%%' THEN '化工'
                                WHEN i.industry LIKE '%%有色%%' THEN '有色金属'
                                WHEN i.industry LIKE '%%军工%%' THEN '国防军工'
                                WHEN i.industry LIKE '%%电气%%' THEN '电力设备'
                                ELSE NULL END AS sw_industry
                    FROM trade_stock_info i
                    WHERE i.stock_code LIKE '688%%'
                       OR i.stock_code LIKE '300%%'
                       OR i.stock_code LIKE '301%%'
                """
                df = pd.read_sql(sql2, conn)
                df = df[df['sw_industry'].notna()]
                df = df[~df['stock_name'].str.contains('ST', na=False)]
            finally:
                conn.close()
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            return pd.DataFrame()

    if df.empty:
        logger.warning("Empty hardtech universe")
        return df

    logger.info(f"Hardtech universe: {len(df)} stocks across "
                f"{df['sw_industry'].nunique()} industries")
    return df
