# -*- coding: utf-8 -*-
"""
Hard-tech production screener

Provides screen_hardtech_stocks() for Celery task integration.
Returns Top N hard-tech stocks with composite factor scores.
"""
import logging

import pandas as pd

from config.db import execute_query

logger = logging.getLogger(__name__)


def screen_hardtech_stocks(trade_date=None, top_n=20, env='online'):
    """
    Hard-tech stock screening main function.

    Args:
        trade_date: str YYYY-MM-DD, None = latest trade date
        top_n: number of stocks to select
        env: database environment

    Returns:
        DataFrame with columns: stock_code, stock_name, industry, composite_score,
        rd_intensity, rd_growth, rd_efficiency, gross_margin_trend,
        revenue_growth, gross_margin, net_profit_growth,
        rps_250, mom_20, pe_ttm
    """
    from strategist.hard_tech.config import (
        FACTOR_GROUPS, FACTOR_DIRECTIONS, INDUSTRY_MAX_WEIGHT,
        RD_INTENSITY_THRESHOLD,
    )
    from strategist.hard_tech.data_loader import (
        load_single_day_factors, load_hardtech_universe,
    )
    from strategist.multi_factor.scorer import FactorSelector

    # Determine trade date
    if trade_date is None:
        rows = execute_query(
            "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily",
            env=env,
        )
        if not rows or not rows[0].get('max_date'):
            logger.error("Cannot determine latest trade date")
            return pd.DataFrame()
        trade_date = str(rows[0]['max_date'])

    logger.info(f"[HARDTECH] Screening for {trade_date}, top_n={top_n}, env={env}")

    # Load universe
    universe = load_hardtech_universe(env=env)
    if universe.empty:
        logger.error("[HARDTECH] Empty universe")
        return pd.DataFrame()

    stock_codes = universe['stock_code'].tolist()
    industry_map = dict(zip(universe['stock_code'], universe['sw_industry']))
    name_map = dict(zip(universe['stock_code'], universe['stock_name']))

    # Load factors for this date
    factors_df = load_single_day_factors(trade_date, stock_codes, env=env)
    if factors_df.empty:
        logger.error(f"[HARDTECH] No factor data for {trade_date}")
        return pd.DataFrame()

    # Intersect with universe
    common_codes = set(stock_codes) & set(factors_df.index)
    factors_df = factors_df.loc[factors_df.index.isin(common_codes)]

    logger.info(f"[HARDTECH] {len(factors_df)} stocks with factor data")

    # R&D intensity filter: keep stocks with rd_intensity >= threshold OR no rd data
    # Stocks without rd data are kept to avoid missing potential gems
    if 'rd_intensity' in factors_df.columns:
        before_rd = len(factors_df)
        factors_df = factors_df[
            factors_df['rd_intensity'].isna() | (factors_df['rd_intensity'] >= RD_INTENSITY_THRESHOLD)
        ]
        logger.info(f"[HARDTECH] RD filter (>= {RD_INTENSITY_THRESHOLD:.1%}): "
                    f"{len(factors_df)}/{before_rd} stocks passed")

    # Score
    selector = FactorSelector(
        use_groups=True,
        factor_groups=FACTOR_GROUPS,
        factor_directions=FACTOR_DIRECTIONS,
    )
    scores = selector.score_cross_section(factors_df)
    ranked = scores.sort_values(ascending=False)

    # Apply industry cap
    industry_cap = max(1, int(top_n * INDUSTRY_MAX_WEIGHT))
    industry_count = {}
    selected = []

    for code in ranked.index:
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

    # Build result DataFrame
    display_factors = [
        'rd_intensity', 'rd_growth', 'rd_efficiency', 'gross_margin_trend',
        'revenue_growth', 'gross_margin', 'net_profit_growth',
        'rps_250', 'mom_20', 'pe_ttm',
    ]

    records = []
    for code in selected:
        record = {
            'stock_code': code,
            'stock_name': name_map.get(code, ''),
            'industry': industry_map.get(code, ''),
            'composite_score': round(float(scores.get(code, 0)), 4),
        }
        for f in display_factors:
            if f in factors_df.columns and code in factors_df.index:
                v = factors_df.loc[code, f]
                record[f] = round(float(v), 4) if pd.notna(v) else None
            else:
                record[f] = None
        records.append(record)

    result = pd.DataFrame(records)

    # Count "innovation leaders" and "value stocks" for DB fields
    # momentum_count = stocks with high innovation group score
    # reversal_count = stocks with low PE (value)
    innovation_leaders = 0
    value_stocks = 0
    for code in selected:
        innovation_factors = ['rd_intensity', 'rd_growth', 'rd_efficiency', 'gross_margin_trend']
        val_factors = [f for f in innovation_factors if f in factors_df.columns]
        if val_factors:
            avg_innovation = factors_df.loc[code, val_factors].mean()
            if pd.notna(avg_innovation) and avg_innovation > 0:
                innovation_leaders += 1
        if 'pe_ttm' in factors_df.columns and code in factors_df.index:
            pe = factors_df.loc[code, 'pe_ttm']
            if pd.notna(pe) and pe > 0 and pe < 50:
                value_stocks += 1

    logger.info(f"[HARDTECH] Selected {len(selected)} stocks "
                f"(innovation_leaders={innovation_leaders}, value_stocks={value_stocks})")

    result.attrs['innovation_leaders'] = innovation_leaders
    result.attrs['value_stocks'] = value_stocks

    return result
