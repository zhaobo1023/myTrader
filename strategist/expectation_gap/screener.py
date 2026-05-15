# -*- coding: utf-8 -*-
"""
Expectation Gap stock screener (Piotroski & So 2017)

Core idea: market systematically misprices stocks whose fundamental quality
diverges from what valuation multiples imply.

Strategy:
1. Compute F-Score (Piotroski 2000) for all stocks
2. Classify by PB percentile:
   - Low PB  (< 30th percentile) = "Value" group
   - High PB (> 70th percentile) = "Glamour" group
3. Identify mispricing:
   - UNDERVALUED:  Low PB + High F-Score (>= 7) -- cheap AND fundamentally strong
   - OVERVALUED:   High PB + Low F-Score (<= 3)  -- expensive AND fundamentally weak
4. Return Top 30 for each group
"""

import logging

import numpy as np
import pandas as pd

from config.db import execute_query
from strategist.expectation_gap.calculator import compute_f_score_for_stocks

logger = logging.getLogger(__name__)

# Default parameters
TOP_N = 30
VALUE_PB_PERCENTILE = 30    # Low PB threshold: bottom 30%
GLAMOUR_PB_PERCENTILE = 70  # High PB threshold: top 30%
UNDERVALUED_MIN_FSCORE = 7  # High F-Score for undervalued
OVERVALUED_MAX_FSCORE = 3   # Low F-Score for overvalued
INDUSTRY_MAX_WEIGHT = 0.20  # Max 20% from any single industry


def load_pb_data(trade_date, env='online'):
    """Load PB data for all stocks on a given trade date."""
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


def load_industry_map(stock_codes, env='online'):
    """Load industry classification for stocks."""
    if not stock_codes:
        return {}
    placeholders = ','.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, industry
        FROM trade_stock_info
        WHERE stock_code IN ({placeholders})
    """
    rows = execute_query(sql, list(stock_codes), env=env)
    if not rows:
        # Fallback: try sw_level1 from trade_stock_financial
        sql2 = f"""
            SELECT DISTINCT stock_code, sw_level1 AS industry
            FROM trade_stock_financial
            WHERE stock_code IN ({placeholders})
              AND sw_level1 IS NOT NULL
        """
        rows = execute_query(sql2, list(stock_codes), env=env)
    return {r['stock_code']: r.get('industry', '') for r in (rows or [])}


def _apply_industry_cap(df, top_n, industry_col='industry'):
    """Limit per-industry weight to INDUSTRY_MAX_WEIGHT."""
    if df.empty or industry_col not in df.columns:
        return df.head(top_n)

    industry_cap = max(1, int(top_n * INDUSTRY_MAX_WEIGHT))
    industry_count = {}
    selected = []

    for _, row in df.iterrows():
        ind = row.get(industry_col) or 'Unknown'
        count = industry_count.get(ind, 0)
        if count < industry_cap:
            selected.append(row.name)
            industry_count[ind] = count + 1
        if len(selected) >= top_n:
            break

    return df.loc[selected]


def screen_expectation_gap(trade_date=None, top_n=TOP_N, env='online'):
    """
    Main screening function: find mispriced stocks via expectation gap.

    Args:
        trade_date: str YYYY-MM-DD, None = latest trade date
        top_n: max stocks per group (undervalued / overvalued)
        env: database environment

    Returns:
        tuple of (undervalued_df, overvalued_df), each with columns:
          stock_code, stock_name, industry, f_score, signal_type,
          pb, pe_ttm, total_mv, plus individual score columns
    """
    # Determine trade date
    if trade_date is None:
        rows = execute_query(
            "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily_basic",
            env=env,
        )
        if not rows or not rows[0].get('max_date'):
            logger.error("[EXPECT-GAP] Cannot determine latest trade date")
            return pd.DataFrame(), pd.DataFrame()
        trade_date = str(rows[0]['max_date'])

    # Fallback if sparse data
    pb_df = load_pb_data(trade_date, env=env)
    if len(pb_df) < 100:
        fallback_rows = execute_query(
            """
            SELECT trade_date, COUNT(*) as cnt
            FROM trade_stock_daily_basic
            WHERE pb IS NOT NULL AND pb > 0
            GROUP BY trade_date
            HAVING cnt >= 1000
            ORDER BY trade_date DESC
            LIMIT 5
            """,
            env=env,
        )
        for fb in (fallback_rows or []):
            fb_date = str(fb['trade_date'])
            pb_df = load_pb_data(fb_date, env=env)
            if len(pb_df) >= 1000:
                logger.info(f"[EXPECT-GAP] Fallback to {fb_date}: {len(pb_df)} stocks")
                trade_date = fb_date
                break

    if pb_df.empty or len(pb_df) < 100:
        logger.error(f"[EXPECT-GAP] Insufficient PB data ({len(pb_df)} stocks)")
        return pd.DataFrame(), pd.DataFrame()

    logger.info(f"[EXPECT-GAP] Screening for {trade_date}, {len(pb_df)} stocks with PB data")

    # Compute PB percentile thresholds
    value_pb_threshold = np.percentile(pb_df['pb'].dropna(), VALUE_PB_PERCENTILE)
    glamour_pb_threshold = np.percentile(pb_df['pb'].dropna(), GLAMOUR_PB_PERCENTILE)
    logger.info(f"[EXPECT-GAP] PB thresholds: value < {value_pb_threshold:.2f}, "
                f"glamour > {glamour_pb_threshold:.2f}")

    # Classify by PB
    low_pb = pb_df[pb_df['pb'] <= value_pb_threshold].copy()
    high_pb = pb_df[pb_df['pb'] >= glamour_pb_threshold].copy()
    logger.info(f"[EXPECT-GAP] Low PB (value): {len(low_pb)}, High PB (glamour): {len(high_pb)}")

    # Compute F-Score for all relevant stocks
    all_codes = list(set(low_pb['stock_code'].tolist() + high_pb['stock_code'].tolist()))
    f_score_df = compute_f_score_for_stocks(all_codes, env=env)

    if f_score_df.empty:
        logger.error("[EXPECT-GAP] No F-Score data computed")
        return pd.DataFrame(), pd.DataFrame()

    # Merge and classify
    # --- Undervalued: Low PB + High F-Score ---
    undervalued = low_pb.merge(f_score_df, on='stock_code', how='inner')
    undervalued = undervalued[undervalued['f_score'] >= UNDERVALUED_MIN_FSCORE].copy()
    undervalued['signal_type'] = 'undervalued'
    logger.info(f"[EXPECT-GAP] Undervalued candidates: {len(undervalued)} "
                f"(Low PB + F-Score >= {UNDERVALUED_MIN_FSCORE})")

    # --- Overvalued: High PB + Low F-Score ---
    overvalued = high_pb.merge(f_score_df, on='stock_code', how='inner')
    overvalued = overvalued[overvalued['f_score'] <= OVERVALUED_MAX_FSCORE].copy()
    overvalued['signal_type'] = 'overvalued'
    logger.info(f"[EXPECT-GAP] Overvalued candidates: {len(overvalued)} "
                f"(High PB + F-Score <= {OVERVALUED_MAX_FSCORE})")

    # Add industry info
    all_selected_codes = list(set(
        undervalued['stock_code'].tolist() + overvalued['stock_code'].tolist()
    ))
    industry_map = load_industry_map(all_selected_codes, env=env)
    name_map = load_stock_names(all_selected_codes, env=env)

    for df in [undervalued, overvalued]:
        df['industry'] = df['stock_code'].map(industry_map).fillna('')
        df['stock_name'] = df['stock_code'].map(name_map).fillna('')

    # Sort and apply industry cap
    undervalued = undervalued.sort_values('f_score', ascending=False)
    undervalued = _apply_industry_cap(undervalued, top_n).reset_index(drop=True)

    overvalued = overvalued.sort_values('f_score', ascending=True)
    overvalued = _apply_industry_cap(overvalued, top_n).reset_index(drop=True)

    logger.info(f"[EXPECT-GAP] Final: {len(undervalued)} undervalued, "
                f"{len(overvalued)} overvalued")

    return undervalued, overvalued
