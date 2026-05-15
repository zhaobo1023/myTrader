# -*- coding: utf-8 -*-
"""
F-Score calculator (Piotroski 2000)

Computes 9 binary signals from financial data:

Profitability (4 signals):
  1. ROA > 0
  2. CFOA (operating cashflow / total assets) > 0
  3. Accrual = CFOA - ROA > 0  (positive when cash flow exceeds accounting earnings)
  4. Delta ROA > 0  (ROA improving)

Leverage / Liquidity / Source of Funds (3 signals):
  5. Delta Leverage < 0  (deleveraging, i.e. long-term debt ratio decreasing)
  6. Delta Liquidity > 0  (current ratio improving)
  7. Equity Offer = 0  (no new shares issued, or shares outstanding not increasing)

Operating Efficiency (2 signals):
  8. Delta Gross Margin > 0  (gross margin improving)
  9. Delta Asset Turnover > 0  (revenue / total assets improving)

Total F-Score = sum of 9 signals, range [0, 9].

Data sources (all from trade_stock_financial):
  - roe, net_profit, revenue, gross_margin, operating_cashflow, eps, total_equity
  - total_assets  (debt_ratio and current_ratio computed from total_equity/total_assets)

Supplemented by trade_stock_daily_basic for market-cap / PB context.
"""

import logging

import pandas as pd

from config.db import execute_query

logger = logging.getLogger(__name__)

# We need at least 2 consecutive quarters to compute deltas.
# Loading 8 quarters (2 years) gives us the current quarter + 7 prior quarters,
# enough for YoY deltas and stability.
QUARTERS_TO_LOAD = 8


def load_financial_data(stock_codes, env='online'):
    """
    Load recent financial data for F-Score calculation.

    Returns:
        DataFrame with columns:
          stock_code, report_date, roe, net_profit, revenue, gross_margin,
          operating_cashflow, eps, total_equity, total_assets, current_ratio
    """
    if not stock_codes:
        return pd.DataFrame()

    placeholders = ','.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, report_date, roe, net_profit, revenue,
               gross_margin, operating_cashflow, eps, total_equity,
               total_assets, current_ratio, debt_ratio
        FROM trade_stock_financial
        WHERE stock_code IN ({placeholders})
        ORDER BY stock_code, report_date DESC
    """
    rows = execute_query(sql, list(stock_codes), env=env)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    numeric_cols = ['roe', 'net_profit', 'revenue', 'gross_margin',
                    'operating_cashflow', 'eps', 'total_equity',
                    'total_assets', 'current_ratio', 'debt_ratio']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df['report_date'] = pd.to_datetime(df['report_date'])
    return df


def compute_f_score(financial_df):
    """
    Compute F-Score for each stock based on the most recent 2 quarters.

    Args:
        financial_df: output of load_financial_data()

    Returns:
        DataFrame with columns:
          stock_code, f_score,
          s_roa, s_cfoa, s_accrual, s_d_roa,
          s_d_leverage, s_d_liquidity, s_equity_offer,
          s_d_gm, s_d_turnover
    """
    if financial_df.empty:
        return pd.DataFrame()

    results = []

    for stock_code, group in financial_df.groupby('stock_code'):
        group = group.sort_values('report_date', ascending=False).head(QUARTERS_TO_LOAD)
        if len(group) < 2:
            continue

        cur = group.iloc[0]
        prev = group.iloc[1]

        score = {}
        score['stock_code'] = stock_code

        # --- Profitability ---

        # 1. ROA > 0
        # Use net_profit / total_assets if total_assets available, else ROE as proxy
        roa = None
        if pd.notna(cur.get('net_profit')) and pd.notna(cur.get('total_assets')) and cur['total_assets'] != 0:
            roa = cur['net_profit'] / cur['total_assets']
        elif pd.notna(cur.get('roe')):
            # Use ROE as proxy (ROE and ROA directionally correlated)
            roa = cur['roe'] / 100.0  # roe is stored as percentage

        score['s_roa'] = 1 if roa is not None and roa > 0 else 0

        # 2. CFOA > 0 (operating cashflow / total assets)
        cfoa = None
        if pd.notna(cur.get('operating_cashflow')) and pd.notna(cur.get('total_assets')) and cur['total_assets'] != 0:
            cfoa = cur['operating_cashflow'] / cur['total_assets']
        elif pd.notna(cur.get('operating_cashflow')) and pd.notna(cur.get('total_equity')) and cur['total_equity'] != 0:
            cfoa = cur['operating_cashflow'] / cur['total_equity']

        score['s_cfoa'] = 1 if cfoa is not None and cfoa > 0 else 0

        # 3. Accrual = CFOA - ROA > 0
        accrual = None
        if cfoa is not None and roa is not None:
            accrual = cfoa - roa
        score['s_accrual'] = 1 if accrual is not None and accrual > 0 else 0

        # 4. Delta ROA > 0
        prev_roa = None
        if pd.notna(prev.get('net_profit')) and pd.notna(prev.get('total_assets')) and prev['total_assets'] != 0:
            prev_roa = prev['net_profit'] / prev['total_assets']
        elif pd.notna(prev.get('roe')):
            prev_roa = prev['roe'] / 100.0

        delta_roa = None
        if roa is not None and prev_roa is not None:
            delta_roa = roa - prev_roa
        score['s_d_roa'] = 1 if delta_roa is not None and delta_roa > 0 else 0

        # --- Leverage / Liquidity / Source of Funds ---

        # 5. Delta Leverage < 0 (deleveraging)
        # debt_ratio column is all NULL, so compute: 1 - total_equity / total_assets
        cur_lev = None
        prev_lev = None
        if (pd.notna(cur.get('total_equity')) and pd.notna(cur.get('total_assets'))
                and cur['total_assets'] != 0):
            cur_lev = 1.0 - cur['total_equity'] / cur['total_assets']
        if (pd.notna(prev.get('total_equity')) and pd.notna(prev.get('total_assets'))
                and prev['total_assets'] != 0):
            prev_lev = 1.0 - prev['total_equity'] / prev['total_assets']
        delta_leverage = None
        if cur_lev is not None and prev_lev is not None:
            delta_leverage = cur_lev - prev_lev
        score['s_d_leverage'] = 1 if delta_leverage is not None and delta_leverage < 0 else 0

        # 6. Delta Liquidity > 0 (equity ratio improving as proxy)
        # current_ratio column is all NULL, use equity/assets ratio as liquidity proxy
        cur_eq_ratio = None
        prev_eq_ratio = None
        if (pd.notna(cur.get('total_equity')) and pd.notna(cur.get('total_assets'))
                and cur['total_assets'] != 0):
            cur_eq_ratio = cur['total_equity'] / cur['total_assets']
        if (pd.notna(prev.get('total_equity')) and pd.notna(prev.get('total_assets'))
                and prev['total_assets'] != 0):
            prev_eq_ratio = prev['total_equity'] / prev['total_assets']
        delta_liquidity = None
        if cur_eq_ratio is not None and prev_eq_ratio is not None:
            delta_liquidity = cur_eq_ratio - prev_eq_ratio
        score['s_d_liquidity'] = 1 if delta_liquidity is not None and delta_liquidity > 0 else 0

        # 7. Equity Offer = 0 (no new equity issued; use total_equity change as proxy)
        # If total_equity grew only via retained earnings (net_profit), that's OK.
        # If total_equity grew much more than net_profit, likely equity issuance.
        equity_offer = 0  # default: no issuance detected
        if pd.notna(cur.get('total_equity')) and pd.notna(prev.get('total_equity')) and prev['total_equity'] > 0:
            equity_change = cur['total_equity'] - prev['total_equity']
            net_profit_val = cur.get('net_profit', 0) or 0
            # If equity increased more than net_profit suggests, likely issuance
            if equity_change > 0 and net_profit_val > 0 and equity_change > net_profit_val * 1.5:
                equity_offer = 1
            elif equity_change > 0 and net_profit_val <= 0:
                equity_offer = 1
        score['s_equity_offer'] = 1 if equity_offer == 0 else 0

        # --- Operating Efficiency ---

        # 8. Delta Gross Margin > 0
        delta_gm = None
        if pd.notna(cur.get('gross_margin')) and pd.notna(prev.get('gross_margin')):
            delta_gm = cur['gross_margin'] - prev['gross_margin']
        score['s_d_gm'] = 1 if delta_gm is not None and delta_gm > 0 else 0

        # 9. Delta Asset Turnover > 0 (revenue / total_assets)
        cur_turnover = None
        prev_turnover = None
        if pd.notna(cur.get('revenue')) and pd.notna(cur.get('total_assets')) and cur['total_assets'] != 0:
            cur_turnover = cur['revenue'] / cur['total_assets']
        if pd.notna(prev.get('revenue')) and pd.notna(prev.get('total_assets')) and prev['total_assets'] != 0:
            prev_turnover = prev['revenue'] / prev['total_assets']
        delta_turnover = None
        if cur_turnover is not None and prev_turnover is not None:
            delta_turnover = cur_turnover - prev_turnover
        score['s_d_turnover'] = 1 if delta_turnover is not None and delta_turnover > 0 else 0

        # Total F-Score
        score['f_score'] = (
            score['s_roa'] + score['s_cfoa'] + score['s_accrual'] + score['s_d_roa'] +
            score['s_d_leverage'] + score['s_d_liquidity'] + score['s_equity_offer'] +
            score['s_d_gm'] + score['s_d_turnover']
        )

        results.append(score)

    return pd.DataFrame(results)


def compute_f_score_for_stocks(stock_codes, env='online'):
    """
    Compute F-Score for a list of stocks.

    Args:
        stock_codes: list of stock code strings
        env: database environment

    Returns:
        DataFrame with F-Score columns per stock
    """
    financial_df = load_financial_data(stock_codes, env=env)
    if financial_df.empty:
        logger.warning("[F-SCORE] No financial data loaded")
        return pd.DataFrame()

    result = compute_f_score(financial_df)
    logger.info(f"[F-SCORE] Computed F-Score for {len(result)} stocks")
    return result
