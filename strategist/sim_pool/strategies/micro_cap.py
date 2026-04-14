# -*- coding: utf-8 -*-
"""Micro-cap strategy adapter: circ market cap < 50bn, liquidity filter."""

import json
import logging
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config.db import execute_query
from strategist.sim_pool.strategies.base import BaseStrategyAdapter

logger = logging.getLogger('myTrader.sim_pool')

# Circ market cap threshold in yi yuan (100M)
_DEFAULT_MAX_CIRC_MV = 50.0      # 50 yi = 5bn CNY
_DEFAULT_MIN_AMT_60D = 1000.0    # min avg daily turnover: 1000 wan yuan


class MicroCapAdapter(BaseStrategyAdapter):
    """
    Micro-cap screener using trade_stock_daily_basic + trade_stock_daily.

    Criteria:
        1. circ_mv < max_circ_mv (default 50 yi)
        2. avg_amount_60d >= min_amt_60d (default 1000 wan)
        3. close > ma20 (short-term uptrend)
        4. Not ST (stock_name not containing 'ST')
    """

    def strategy_type(self) -> str:
        return 'micro_cap'

    def run(self, signal_date: str, params: dict) -> pd.DataFrame:
        """
        params:
            max_circ_mv:  float, max circulating market cap in yi yuan (default 50)
            min_amt_60d:  float, min avg 60d turnover in wan yuan (default 1000)
            max_results:  int (default 30)
        """
        max_circ_mv = float(params.get('max_circ_mv', _DEFAULT_MAX_CIRC_MV))
        min_amt_60d = float(params.get('min_amt_60d', _DEFAULT_MIN_AMT_60D))
        max_results = int(params.get('max_results', 30))
        env = params.get('db_env', 'online')

        # --- Step 1: filter by circ_mv from daily_basic ---
        basic_rows = execute_query(
            """
            SELECT b.stock_code, b.stock_name, b.circ_mv, b.close,
                   b.pe_ttm, b.pb
            FROM trade_stock_daily_basic b
            WHERE b.trade_date = %s
              AND b.circ_mv IS NOT NULL
              AND b.circ_mv < %s
              AND b.stock_name NOT LIKE '%%ST%%'
            ORDER BY b.circ_mv ASC
            LIMIT 500
            """,
            (signal_date, max_circ_mv * 1e8),   # circ_mv stored in yuan
            env=env,
        )

        if not basic_rows:
            # Fallback: circ_mv may be stored in yi yuan already
            basic_rows = execute_query(
                """
                SELECT b.stock_code, b.stock_name, b.circ_mv, b.close,
                       b.pe_ttm, b.pb
                FROM trade_stock_daily_basic b
                WHERE b.trade_date = %s
                  AND b.circ_mv IS NOT NULL
                  AND b.circ_mv < %s
                  AND b.stock_name NOT LIKE '%%ST%%'
                ORDER BY b.circ_mv ASC
                LIMIT 500
                """,
                (signal_date, max_circ_mv),
                env=env,
            )

        if not basic_rows:
            logger.info('[MicroCapAdapter] no basic data on %s', signal_date)
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        codes = [r['stock_code'] for r in basic_rows]

        # --- Step 2: liquidity + MA20 filter from trade_stock_daily ---
        if not codes:
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        placeholders = ','.join(['%s'] * len(codes))
        daily_rows = execute_query(
            f"""
            SELECT d.stock_code,
                   AVG(d.amount) AS avg_amount_60d,
                   MAX(CASE WHEN d.trade_date = %s THEN d.close END) AS close_today,
                   AVG(CASE WHEN d.trade_date <= %s THEN d.close END) AS ma20_approx
            FROM trade_stock_daily d
            WHERE d.stock_code IN ({placeholders})
              AND d.trade_date BETWEEN DATE_SUB(%s, INTERVAL 90 DAY) AND %s
            GROUP BY d.stock_code
            HAVING avg_amount_60d >= %s
               AND close_today IS NOT NULL
               AND close_today > ma20_approx
            """,
            tuple([signal_date, signal_date] + codes + [signal_date, signal_date,
                   min_amt_60d * 10000]),   # convert wan to yuan
            env=env,
        )

        if not daily_rows:
            return pd.DataFrame(columns=['stock_code', 'stock_name'])

        passed_codes = {r['stock_code'] for r in daily_rows}
        daily_map = {r['stock_code']: r for r in daily_rows}

        result_rows = [r for r in basic_rows if r['stock_code'] in passed_codes]
        result_rows = result_rows[:max_results]

        records = []
        for r in result_rows:
            code = r['stock_code']
            daily = daily_map.get(code, {})
            meta = {
                'circ_mv': r.get('circ_mv'),
                'pe_ttm': r.get('pe_ttm'),
                'pb': r.get('pb'),
                'avg_amount_60d': daily.get('avg_amount_60d'),
                'close': r.get('close'),
            }
            records.append({
                'stock_code': code,
                'stock_name': r.get('stock_name', code),
                'signal_meta': json.dumps(meta, ensure_ascii=False, default=str),
            })

        df = pd.DataFrame(records)
        logger.info('[MicroCapAdapter] %d micro-cap stocks on %s', len(df), signal_date)
        return df
