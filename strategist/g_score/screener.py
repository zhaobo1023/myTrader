# -*- coding: utf-8 -*-
"""
G-Score stock screener

Selects high-quality stocks among high-valuation (high PB) names
using G-Score (Mohanram 2005).

Strategy logic:
1. Define high-valuation universe: PB > 70th percentile of all stocks
2. Compute G-Score for all stocks
3. Filter to high-valuation universe
4. Select top stocks by G-Score (>= 6 = high G-Score group)
5. Apply industry cap for diversification
"""

import logging

import numpy as np
import pandas as pd

from config.db import execute_query
from strategist.g_score.calculator import compute_g_score_for_stocks

logger = logging.getLogger(__name__)

# Default parameters
TOP_N = 30
PB_PERCENTILE = 70  # High PB threshold: top 30% by PB
MIN_G_SCORE = 5     # Minimum G-Score to qualify (high group: 6-8, medium-high: 5)
INDUSTRY_MAX_WEIGHT = 0.20  # Max 20% from any single industry


def load_pb_data(trade_date, env='online'):
    """
    Load PB (price-to-book) data for all stocks on a given trade date.

    Returns:
        DataFrame with columns: stock_code, pb, pe_ttm, total_mv
    """
    sql = """
        SELECT stock_code, pb, pe_ttm, total_mv
        FROM trade_stock_daily_basic
        WHERE trade_date = %s
          AND pb IS NOT NULL
          AND pb > 0
        ORDER BY stock_code
    """
    rows = execute_query(sql, (trade_date,), env=env)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in ['pb', 'pe_ttm', 'total_mv']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def load_stock_names(stock_codes, env='online'):
    """Load stock names for display."""
    if not stock_codes:
        return {}

    placeholders = ','.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, stock_name
        FROM trade_stock_basic
        WHERE stock_code IN ({placeholders})
    """
    rows = execute_query(sql, list(stock_codes), env=env)
    return {r['stock_code']: r.get('stock_name', '') for r in (rows or [])}


def screen_g_score_stocks(trade_date=None, top_n=TOP_N, min_g_score=MIN_G_SCORE,
                          pb_percentile=PB_PERCENTILE, env='online'):
    """
    Main screening function: find high-G-Score stocks in high-PB universe.

    Args:
        trade_date: str YYYY-MM-DD, None = latest trade date
        top_n: max number of stocks to return
        min_g_score: minimum G-Score to qualify
        pb_percentile: PB percentile threshold for "high valuation"
        env: database environment

    Returns:
        DataFrame with columns: stock_code, stock_name, industry, g_score,
        pb, pe_ttm, total_mv, plus individual score columns
    """
    # Determine trade date
    if trade_date is None:
        rows = execute_query(
            "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily",
            env=env,
        )
        if not rows or not rows[0].get('max_date'):
            logger.error("[G-SCORE] Cannot determine latest trade date")
            return pd.DataFrame()
        trade_date = str(rows[0]['max_date'])

    logger.info(f"[G-SCORE] Screening for {trade_date}, top_n={top_n}, "
                f"min_g_score={min_g_score}, pb_percentile={pb_percentile}")

    # Load PB data for valuation classification
    pb_df = load_pb_data(trade_date, env=env)
    if pb_df.empty:
        logger.error(f"[G-SCORE] No PB data for {trade_date}")
        return pd.DataFrame()

    logger.info(f"[G-SCORE] PB data: {len(pb_df)} stocks")

    # Compute PB percentile threshold
    pb_threshold = np.percentile(pb_df['pb'].dropna(), pb_percentile)
    logger.info(f"[G-SCORE] PB {pb_percentile}th percentile = {pb_threshold:.2f}")

    # Get all stock codes with financial data
    all_codes = pb_df['stock_code'].tolist()

    # Compute G-Score for all stocks
    g_score_df = compute_g_score_for_stocks(all_codes, env=env)
    if g_score_df.empty:
        logger.error("[G-SCORE] No G-Score data computed")
        return pd.DataFrame()

    # Merge with PB data
    merged = g_score_df.merge(
        pb_df[['stock_code', 'pb', 'pe_ttm', 'total_mv']],
        on='stock_code', how='inner')
    logger.info(f"[G-SCORE] Merged: {len(merged)} stocks with both G-Score and PB data")

    # Filter: high PB (high valuation)
    high_pb = merged[merged['pb'] >= pb_threshold].copy()
    logger.info(f"[G-SCORE] High PB universe (PB >= {pb_threshold:.2f}): {len(high_pb)} stocks")

    if high_pb.empty:
        return pd.DataFrame()

    # Filter: minimum G-Score
    qualified = high_pb[high_pb['g_score'] >= min_g_score].copy()
    logger.info(f"[G-SCORE] G-Score >= {min_g_score}: {len(qualified)} stocks in high-PB universe")

    if qualified.empty:
        logger.info("[G-SCORE] No stocks meet the criteria")
        return pd.DataFrame()

    # Apply industry cap for diversification
    industry_map = dict(zip(qualified['stock_code'], qualified['industry']))
    industry_cap = max(1, int(top_n * INDUSTRY_MAX_WEIGHT))
    industry_count = {}
    selected = []

    for _, row in qualified.sort_values('g_score', ascending=False).iterrows():
        code = row['stock_code']
        ind = industry_map.get(code)
        if ind is None:
            selected.append(code)
            if len(selected) >= top_n:
                break
            continue
        count = industry_count.get(ind, 0)
        if count < industry_cap:
            selected.append(code)
            industry_count[ind] = count + 1
            if len(selected) >= top_n:
                break

    result = qualified[qualified['stock_code'].isin(selected)].copy()
    result = result.sort_values('g_score', ascending=False).reset_index(drop=True)

    # Add stock names
    name_map = load_stock_names(result['stock_code'].tolist(), env=env)
    result['stock_name'] = result['stock_code'].map(name_map).fillna('')

    # Count groups for DB fields
    high_g = int((result['g_score'] >= 6).sum())
    med_g = int(((result['g_score'] >= 4) & (result['g_score'] < 6)).sum())

    logger.info(f"[G-SCORE] Selected {len(result)} stocks "
                f"(high_g={high_g}, med_g={med_g})")

    result.attrs['high_g_score_count'] = high_g
    result.attrs['medium_g_score_count'] = med_g

    return result
