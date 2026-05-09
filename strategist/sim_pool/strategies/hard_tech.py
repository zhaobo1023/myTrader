# -*- coding: utf-8 -*-
"""Hard-tech multi-factor strategy adapter for sim_pool."""

import json
import logging
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config.db import execute_query
from strategist.sim_pool.strategies.base import BaseStrategyAdapter
from strategist.multi_factor.scorer import FactorSelector
from strategist.multi_factor.data_loader import load_stock_filter
from strategist.hard_tech.config import (
    STRATEGY_FACTOR_GROUPS, STRATEGY_FACTOR_DIRECTIONS,
    BACKTEST_PARAMS,
)
from strategist.hard_tech.stock_pool import (
    build_hardtech_universe, get_industry_map, get_stock_names,
)

logger = logging.getLogger('myTrader.sim_pool')


class HardTechAdapter(BaseStrategyAdapter):
    """
    Hard-tech multi-factor screener.

    Criteria:
      1. Belong to hard-tech industries or KCB/CYB boards
      2. R&D intensity >= 3% (if rd data available) or no rd data (potential gems)
      3. Ranked by 5 IC-validated factors: gross_margin, mom_20, roe_ttm, rd_growth, market_cap
      4. Industry cap: single industry <= 20%
    """

    def strategy_type(self) -> str:
        return 'hard_tech'

    def run(self, signal_date: str, params: dict) -> pd.DataFrame:
        """
        params:
            top_n:           int (default 20)
            db_env:          str (default 'online')
        """
        top_n = int(params.get('top_n', BACKTEST_PARAMS['top_n']))
        env = params.get('db_env', 'online')

        # Load factor cross-section for signal_date
        factor_cols = [
            'revenue_growth', 'gross_margin', 'roe_ttm',
            'mom_20', 'market_cap', 'rd_intensity', 'rd_growth',
        ]

        sql_parts = [
            (
                "SELECT e.stock_code, e.revenue_growth, e.gross_margin, e.roe_ttm "
                "FROM trade_stock_extended_factor e "
                "WHERE e.calc_date = %s"
            ),
            (
                "SELECT b.stock_code, b.mom_20 "
                "FROM trade_stock_basic_factor b "
                "WHERE b.calc_date = %s"
            ),
            (
                "SELECT v.stock_code, v.market_cap "
                "FROM trade_stock_valuation_factor v "
                "WHERE v.calc_date = %s"
            ),
            (
                "SELECT h.stock_code, h.rd_intensity, h.rd_growth "
                "FROM trade_stock_hardtech_factor h "
                "WHERE h.calc_date = %s"
            ),
        ]

        dfs = []
        for sql in sql_parts:
            rows = execute_query(sql, (signal_date,), env=env)
            if rows:
                dfs.append(pd.DataFrame(rows))

        if not dfs:
            logger.info('[HardTechAdapter] no data on %s', signal_date)
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        merged = dfs[0]
        for other in dfs[1:]:
            merged = pd.merge(merged, other, on='stock_code', how='outer')

        # Filter to hard-tech universe
        universe = set(build_hardtech_universe())
        merged = merged[merged['stock_code'].isin(universe)]

        if merged.empty:
            logger.info('[HardTechAdapter] no hard-tech stocks on %s', signal_date)
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        # Convert numeric
        for col in factor_cols:
            if col in merged.columns:
                merged[col] = pd.to_numeric(merged[col], errors='coerce')

        # R&D filter: keep if rd_intensity >= 3% or no rd data
        if 'rd_intensity' in merged.columns:
            merged['rd_eligible'] = (
                merged['rd_intensity'].isna() |
                (merged['rd_intensity'] >= 0.03)
            )
            merged = merged[merged['rd_eligible']]
            merged = merged.drop(columns=['rd_eligible'])

        merged = merged.set_index('stock_code')

        # Score and select
        selector = FactorSelector(
            use_groups=True,
            factor_groups=STRATEGY_FACTOR_GROUPS,
            factor_directions=STRATEGY_FACTOR_DIRECTIONS,
        )

        blacklist = load_stock_filter()
        industry_map = get_industry_map()

        top_stocks = selector.select_top_n(
            merged, top_n=top_n,
            blacklist=blacklist,
            industry_map=industry_map,
        )

        if not top_stocks:
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        # Build result
        scores = selector.score_cross_section(merged)
        names = get_stock_names(top_stocks)

        records = []
        for code in top_stocks:
            meta = {
                'composite_score': float(scores.get(code, 0)),
            }
            for col in factor_cols:
                if col in merged.columns and code in merged.index:
                    val = merged.loc[code, col]
                    if pd.notna(val):
                        meta[col] = float(val)

            records.append({
                'stock_code': code,
                'stock_name': names.get(code, code),
                'signal_meta': json.dumps(meta, ensure_ascii=False, default=str),
            })

        df = pd.DataFrame(records)
        logger.info('[HardTechAdapter] %d hard-tech stocks on %s', len(df), signal_date)
        return df
