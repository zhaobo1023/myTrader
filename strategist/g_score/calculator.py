# -*- coding: utf-8 -*-
"""
G-Score calculator

Computes the 8 G-Score indicators from Mohanram (2005), adapted for A-shares.

8 indicators in 3 groups:

Profitability:
  1. ROA          = net_profit(TTM) / avg_total_assets
  2. CFOA         = operating_cashflow(TTM) / avg_total_assets
  3. Accrual      = ROA - CFOA  (lower = better)

Conservative Accounting:
  4. R&D / assets  = rd_expense(TTM) / avg_total_assets
  5. SGA / assets  = selling_expense(TTM) / avg_total_assets
  6. Capex / assets = capex(TTM) / avg_total_assets

Earnings Stability:
  7. ROA variance  = var(quarterly ROA, past 12 quarters)
  8. Revenue growth variance = var(yoy revenue growth, past 12 quarters)

Each indicator (except accrual) is scored 1 if above industry median,
0 otherwise. Accrual is scored 1 if < 0, 0 otherwise.
G-Score = sum of all 8 binary scores (0-8).

Data sources:
  - trade_stock_financial: net_profit, revenue, total_assets
  - financial_income_detail: rd_expense, selling_expense (all A-share, from EM API)
  - financial_cashflow: operating_cashflow, investing_cashflow (proxy for capex)
  - trade_stock_basic: sw_level1 (industry classification)

Approximations for missing data:
  - capex: use abs(investing_cashflow) as proxy
"""

import logging

import numpy as np
import pandas as pd

from config.db import execute_query

logger = logging.getLogger(__name__)

# Minimum number of quarterly reports needed for variance calculation
MIN_QUARTERS_FOR_VARIANCE = 8


def _strip_code_suffix(code):
    """Remove .SZ/.SH/.BJ suffix from stock code for cross-table matching."""
    if code and '.' in code:
        return code.split('.')[0]
    return code


def load_financial_data(stock_codes, env='online'):
    """
    Load quarterly financial data for G-Score calculation.

    Data sources and units:
      - trade_stock_financial: net_profit/revenue/total_assets in YUAN (convert to yi)
      - financial_cashflow: operating/investing cashflow in YI yuan (stock_code without suffix)
      - financial_income_detail: rd_expense/selling_expense in YUAN (convert to yi)

    Returns:
        DataFrame with columns: stock_code, report_date, net_profit, revenue,
        total_assets, operating_cashflow, investing_cashflow, gross_margin, rd_expense
        All monetary values normalized to YI yuan.
    """
    if not stock_codes:
        return pd.DataFrame()

    placeholders = ','.join(['%s'] * len(stock_codes))

    # Load core financials from trade_stock_financial (quarterly, units: yuan)
    sql = f"""
        SELECT f.stock_code, f.report_date,
               f.net_profit, f.revenue,
               f.total_assets,
               f.gross_margin,
               f.roe
        FROM trade_stock_financial f
        WHERE f.stock_code IN ({placeholders})
        ORDER BY f.stock_code, f.report_date ASC
    """
    rows = execute_query(sql, list(stock_codes), env=env)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['report_date'] = pd.to_datetime(df['report_date'])
    for col in ['net_profit', 'revenue', 'total_assets', 'gross_margin', 'roe']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Convert yuan to yi (divide by 1e8)
    for col in ['net_profit', 'revenue', 'total_assets']:
        if col in df.columns:
            df[col] = df[col] / 1e8

    # Add stripped code for cross-table matching
    df['code_stripped'] = df['stock_code'].apply(_strip_code_suffix)

    # Load cashflow from financial_cashflow (annual, units: yi, stock_code without suffix)
    stripped_codes = df['code_stripped'].unique().tolist()
    ph2 = ','.join(['%s'] * len(stripped_codes))
    sql_cf = f"""
        SELECT stock_code, report_date,
               operating_cashflow,
               investing_cashflow
        FROM financial_cashflow
        WHERE stock_code IN ({ph2})
        ORDER BY stock_code, report_date ASC
    """
    cf_rows = execute_query(sql_cf, stripped_codes, env=env)
    if cf_rows:
        df_cf = pd.DataFrame(cf_rows)
        df_cf['report_date'] = pd.to_datetime(df_cf['report_date'])
        for col in ['operating_cashflow', 'investing_cashflow']:
            df_cf[col] = pd.to_numeric(df_cf[col], errors='coerce')
        df_cf = df_cf.rename(columns={'stock_code': 'code_stripped'})

        # merge_asof requires globally sorted on='report_date'
        df = df.sort_values('report_date')
        df_cf = df_cf.sort_values('report_date')

        merged = pd.merge_asof(
            df,
            df_cf[['code_stripped', 'report_date', 'operating_cashflow', 'investing_cashflow']],
            on='report_date',
            by='code_stripped',
            direction='backward'
        )
        df = merged
    else:
        df['operating_cashflow'] = np.nan
        df['investing_cashflow'] = np.nan

    # Load R&D and selling expense from financial_income_detail
    # stock_code in financial_income_detail is bare (no suffix), units are YUAN
    sql_rd = f"""
        SELECT stock_code, report_date,
               rd_expense, selling_expense
        FROM financial_income_detail
        WHERE stock_code IN ({ph2})
          AND (rd_expense IS NOT NULL OR selling_expense IS NOT NULL)
        ORDER BY stock_code, report_date ASC
    """
    rd_rows = execute_query(sql_rd, stripped_codes, env=env)
    if rd_rows:
        df_rd = pd.DataFrame(rd_rows)
        df_rd['report_date'] = pd.to_datetime(df_rd['report_date'])
        for col in ['rd_expense', 'selling_expense']:
            df_rd[col] = pd.to_numeric(df_rd[col], errors='coerce')
            # Convert yuan to yi
            df_rd[col] = df_rd[col] / 1e8
        df_rd = df_rd.rename(columns={'stock_code': 'code_stripped'})
        # merge_asof requires globally sorted on='report_date'
        df_rd = df_rd.sort_values('report_date')
        df = df.sort_values('report_date')
        merged = pd.merge_asof(
            df.drop(columns=['rd_expense', 'selling_expense'], errors='ignore'),
            df_rd[['code_stripped', 'report_date', 'rd_expense', 'selling_expense']],
            on='report_date',
            by='code_stripped',
            direction='backward'
        )
        df = merged
    else:
        df['rd_expense'] = np.nan
        df['selling_expense'] = np.nan

    # Drop helper column
    df = df.drop(columns=['code_stripped'], errors='ignore')
    # Restore sort
    df = df.sort_values(['stock_code', 'report_date']).reset_index(drop=True)

    return df


def load_industry_map(stock_codes, env='online'):
    """Load SW level-1 industry classification for stock codes."""
    if not stock_codes:
        return {}

    placeholders = ','.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, sw_level1
        FROM trade_stock_basic
        WHERE stock_code IN ({placeholders})
          AND sw_level1 IS NOT NULL
    """
    rows = execute_query(sql, list(stock_codes), env=env)
    return {r['stock_code']: r['sw_level1'] for r in (rows or [])}


def compute_quarterly_roa(df):
    """
    Compute quarterly ROA = net_profit(TTM) / avg_total_assets for each row.
    Uses vectorized groupby transform for efficiency.
    """
    df = df.sort_values(['stock_code', 'report_date']).copy()

    # TTM net profit = sum of last 4 quarters (per stock)
    df['ttm_net_profit'] = df.groupby('stock_code')['net_profit'].transform(
        lambda x: x.rolling(4, min_periods=4).sum()
    )

    # Average total assets over 4 quarters
    df['avg_total_assets'] = df.groupby('stock_code')['total_assets'].transform(
        lambda x: x.rolling(4, min_periods=4).mean()
    )

    # ROA = TTM net profit / avg total assets
    df['roa_ttm'] = np.where(
        (df['avg_total_assets'].notna() & (df['avg_total_assets'] != 0)),
        df['ttm_net_profit'] / df['avg_total_assets'],
        np.nan
    )

    return df


def compute_g_score_indicators(df):
    """
    Compute all 8 G-Score indicators per stock per quarter.

    Input: quarterly financial data with stock_code, report_date,
           net_profit, revenue, total_assets, operating_cashflow,
           investing_cashflow, rd_expense

    Output: DataFrame with same rows + indicator columns + 8 score columns
    """
    df = df.copy()

    # --- Group 1: Profitability ---

    # 1. ROA (already computed as roa_ttm via compute_quarterly_roa)
    # Ensure roa_ttm exists
    if 'roa_ttm' not in df.columns:
        df['roa_ttm'] = np.nan

    # 2. CFOA = operating_cashflow / avg_total_assets
    # NOTE: operating_cashflow comes from financial_cashflow (annual-only data).
    # merge_asof backward fills each quarterly row with the latest annual cashflow.
    # Do NOT compute TTM rolling sum for cashflow (would 4x the annual value).
    # Instead, use the annual cashflow directly normalized by avg_total_assets.
    df = df.sort_values(['stock_code', 'report_date'])
    df['cfoa'] = np.where(
        (df['avg_total_assets'].notna() & (df['avg_total_assets'] != 0)),
        df['operating_cashflow'] / df['avg_total_assets'],
        np.nan
    )

    # 3. Accrual = ROA - CFOA (lower is better -> negative means high quality)
    df['accrual'] = df['roa_ttm'] - df['cfoa']

    # --- Group 2: Conservative Accounting ---

    # 4. R&D / avg_total_assets
    if 'rd_expense' not in df.columns:
        df['rd_expense'] = np.nan
    df['ttm_rd'] = df.groupby('stock_code')['rd_expense'].transform(
        lambda x: x.rolling(4, min_periods=4).sum()
    )
    df['rd_ratio'] = np.where(
        (df['avg_total_assets'].notna() & (df['avg_total_assets'] != 0)),
        df['ttm_rd'] / df['avg_total_assets'],
        np.nan
    )

    # 5. SGA (selling expense) / avg_total_assets
    # Use real selling_expense from financial_income_detail where available.
    # Fall back to approximation using gross_margin where not available.
    if 'selling_expense' not in df.columns:
        df['selling_expense'] = np.nan
    df['ttm_sga'] = df.groupby('stock_code')['selling_expense'].transform(
        lambda x: x.rolling(4, min_periods=4).sum()
    )
    # Approximation fallback: (revenue * (1 - gross_margin/100) - net_profit)
    sga_approx = np.where(
        df['revenue'].notna() & df['gross_margin'].notna() & df['net_profit'].notna(),
        (df['revenue'] * (1 - df['gross_margin'] / 100) - df['net_profit']).clip(lower=0),
        np.nan
    )
    df['ttm_sga'] = np.where(
        df['ttm_sga'].notna(),
        df['ttm_sga'],
        sga_approx
    )
    df['sga_ratio'] = np.where(
        (df['avg_total_assets'].notna() & (df['avg_total_assets'] != 0)),
        df['ttm_sga'] / df['avg_total_assets'],
        np.nan
    )

    # 6. Capex / avg_total_assets (use abs(investing_cashflow) as proxy)
    # NOTE: investing_cashflow is annual-only from financial_cashflow.
    # Use the annual value directly (no TTM rolling sum).
    if 'investing_cashflow' not in df.columns:
        df['investing_cashflow'] = np.nan
    df['capex_proxy'] = df['investing_cashflow'].abs()
    df['capex_ratio'] = np.where(
        (df['avg_total_assets'].notna() & (df['avg_total_assets'] != 0)),
        df['capex_proxy'] / df['avg_total_assets'],
        np.nan
    )

    # --- Group 3: Earnings Stability ---
    # Need 12 quarters (3 years) of data

    # 7. ROA variance (quarterly, past 12 quarters)
    df['roa_quarterly'] = np.where(
        (df['total_assets'].notna() & (df['total_assets'] != 0)),
        df['net_profit'] / df['total_assets'],
        np.nan
    )
    df['roa_var'] = df.groupby('stock_code')['roa_quarterly'].transform(
        lambda x: x.rolling(12, min_periods=MIN_QUARTERS_FOR_VARIANCE).var()
    )

    # 8. Revenue growth variance (YoY quarterly, past 12 quarters)
    df['rev_yoy'] = df.groupby('stock_code')['revenue'].transform(
        lambda x: x.pct_change(4, fill_method=None) * 100
    )
    df['rev_yoy'] = df['rev_yoy'].replace([np.inf, -np.inf], np.nan)
    df['rev_growth_var'] = df.groupby('stock_code')['rev_yoy'].transform(
        lambda x: x.rolling(12, min_periods=MIN_QUARTERS_FOR_VARIANCE).var()
    )

    return df


def score_indicators(df, industry_map):
    """
    Score each indicator based on industry median comparison.
    Adds 8 binary score columns (s_roa, s_cfoa, s_accrual, s_rd, s_sga, s_capex, s_roa_var, s_rev_var).

    Args:
        df: DataFrame with indicator columns, must have stock_code
        industry_map: dict {stock_code: industry_name}

    Returns:
        DataFrame with score columns added
    """
    df = df.copy()
    df['industry'] = df['stock_code'].map(industry_map)

    # Industry-level median calculation
    # For each indicator, score 1 if above industry median, 0 otherwise
    # Accrual: score 1 if < 0, 0 otherwise (independent of industry)
    # Variance indicators: score 1 if BELOW industry median (lower variance = better stability)

    indicators_higher_better = ['roa_ttm', 'cfoa', 'rd_ratio', 'sga_ratio', 'capex_ratio']
    indicators_lower_better = ['roa_var', 'rev_growth_var']

    # Compute industry medians
    industry_medians = {}
    for ind in indicators_higher_better + indicators_lower_better:
        if ind in df.columns:
            industry_medians[ind] = df.groupby('industry')[ind].transform('median')

    # Score 1: ROA
    if 'roa_ttm' in df.columns and 'roa_ttm' in industry_medians:
        df['s_roa'] = np.where(
            df['roa_ttm'].notna(),
            (df['roa_ttm'] > industry_medians['roa_ttm']).astype(int),
            0
        )
    else:
        df['s_roa'] = 0

    # Score 2: CFOA (annual data only, NaN -> 0.5 neutral)
    if 'cfoa' in df.columns and 'cfoa' in industry_medians:
        df['s_cfoa'] = np.where(
            df['cfoa'].notna(),
            (df['cfoa'] > industry_medians['cfoa']).astype(int),
            0.5
        )
    else:
        df['s_cfoa'] = 0.5

    # Score 3: Accrual (negative = better, independent of industry)
    df['s_accrual'] = np.where(
        df['accrual'].notna(),
        (df['accrual'] < 0).astype(int),
        0
    )

    # Score 4: R&D ratio
    # When rd_ratio is NaN (no R&D data for this industry), give 0.5 (neutral)
    # so that R&D only differentiates stocks with actual data, not penalize others
    if 'rd_ratio' in df.columns and 'rd_ratio' in industry_medians:
        df['s_rd'] = np.where(
            df['rd_ratio'].notna(),
            (df['rd_ratio'] > industry_medians['rd_ratio']).astype(int),
            0.5
        )
    else:
        df['s_rd'] = 0.5

    # Score 5: SGA ratio
    if 'sga_ratio' in df.columns and 'sga_ratio' in industry_medians:
        df['s_sga'] = np.where(
            df['sga_ratio'].notna(),
            (df['sga_ratio'] > industry_medians['sga_ratio']).astype(int),
            0
        )
    else:
        df['s_sga'] = 0

    # Score 6: Capex ratio (annual data only, NaN -> 0.5 neutral)
    if 'capex_ratio' in df.columns and 'capex_ratio' in industry_medians:
        df['s_capex'] = np.where(
            df['capex_ratio'].notna(),
            (df['capex_ratio'] > industry_medians['capex_ratio']).astype(int),
            0.5
        )
    else:
        df['s_capex'] = 0.5

    # Score 7: ROA variance (lower = better -> below median = 1)
    if 'roa_var' in df.columns and 'roa_var' in industry_medians:
        df['s_roa_var'] = np.where(
            df['roa_var'].notna(),
            (df['roa_var'] < industry_medians['roa_var']).astype(int),
            0
        )
    else:
        df['s_roa_var'] = 0

    # Score 8: Revenue growth variance (lower = better -> below median = 1)
    if 'rev_growth_var' in df.columns and 'rev_growth_var' in industry_medians:
        df['s_rev_var'] = np.where(
            df['rev_growth_var'].notna(),
            (df['rev_growth_var'] < industry_medians['rev_growth_var']).astype(int),
            0
        )
    else:
        df['s_rev_var'] = 0

    # Total G-Score
    score_cols = ['s_roa', 's_cfoa', 's_accrual', 's_rd', 's_sga', 's_capex',
                  's_roa_var', 's_rev_var']
    df['g_score'] = df[score_cols].sum(axis=1)

    return df


def compute_g_score_for_stocks(stock_codes, env='online'):
    """
    Main entry: compute G-Score for a list of stocks using latest available data.

    Returns:
        DataFrame with columns: stock_code, g_score, s_roa, s_cfoa, s_accrual,
        s_rd, s_sga, s_capex, s_roa_var, s_rev_var, plus underlying indicator values
    """
    if not stock_codes:
        return pd.DataFrame()

    logger.info(f"[G-SCORE] Loading financial data for {len(stock_codes)} stocks...")
    df = load_financial_data(list(stock_codes), env=env)
    if df.empty:
        logger.warning("[G-SCORE] No financial data available")
        return pd.DataFrame()

    logger.info(f"[G-SCORE] Loaded {len(df)} quarterly records for {df['stock_code'].nunique()} stocks")

    # Compute quarterly ROA (TTM)
    df = compute_quarterly_roa(df)

    # Compute all indicators
    logger.info("[G-SCORE] Computing G-Score indicators...")
    df = compute_g_score_indicators(df)

    # Take only the latest quarter per stock
    df_latest = df.sort_values('report_date').groupby('stock_code').last().reset_index()
    logger.info(f"[G-SCORE] Latest quarter data: {len(df_latest)} stocks")

    # Load industry map
    industry_map = load_industry_map(list(df_latest['stock_code']), env=env)
    logger.info(f"[G-SCORE] Industry mapping: {len(industry_map)} stocks with industry info")

    # Score indicators
    df_scored = score_indicators(df_latest, industry_map)

    # Select output columns
    output_cols = ['stock_code', 'report_date', 'industry',
                   'roa_ttm', 'cfoa', 'accrual',
                   'rd_ratio', 'sga_ratio', 'capex_ratio',
                   'roa_var', 'rev_growth_var',
                   's_roa', 's_cfoa', 's_accrual', 's_rd',
                   's_sga', 's_capex', 's_roa_var', 's_rev_var',
                   'g_score']

    available_cols = [c for c in output_cols if c in df_scored.columns]
    result = df_scored[available_cols].copy()

    # Sort by g_score descending
    result = result.sort_values('g_score', ascending=False).reset_index(drop=True)

    logger.info(f"[G-SCORE] Scored {len(result)} stocks, "
                f"G-Score range: [{result['g_score'].min()}-{result['g_score'].max()}], "
                f"median: {result['g_score'].median():.1f}")

    return result
