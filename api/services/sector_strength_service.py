# -*- coding: utf-8 -*-
"""
Sector strength query service.

Provides read-only access to trade_sector_strength_daily and
trade_morning_picks for the morning briefing and agent tools.
"""
import logging
from datetime import date
from typing import Optional

from config.db import execute_query

logger = logging.getLogger(__name__)


def get_latest_strength(
    sw_level: int = 2,
    top_n: int = 10,
    trade_date: Optional[str] = None,
    phase_filter: Optional[str] = None,
    env: str = 'online',
) -> dict:
    """
    Query latest sector strength data.

    Args:
        sw_level:    1 or 2 (default 2)
        top_n:       number of top-ranked sectors to return (default 10)
        trade_date:  'YYYY-MM-DD' or None (use most recent available date)
        phase_filter: filter by phase e.g. 'accel_up', or None for all
        env:         DB environment

    Returns dict:
        {
            'trade_date': str,
            'sectors': [
                {
                    'sector_code', 'sector_name', 'parent_name',
                    'mom_21', 'rs_60', 'vol_ratio',
                    'composite_score', 'score_rank',
                    'phase', 'is_inflection', 'inflection_type'
                },
                ...
            ],
            'inflections': [same fields, only rows where is_inflection=1]
        }
    """
    # Resolve trade_date
    if trade_date is None:
        rows = execute_query(
            "SELECT MAX(trade_date) AS d FROM trade_sector_strength_daily WHERE sw_level = %s",
            (sw_level,),
            env=env,
        )
        if not rows or rows[0]['d'] is None:
            return {'trade_date': None, 'sectors': [], 'inflections': []}
        trade_date = str(rows[0]['d'])

    # Build query
    phase_clause = ''
    params: tuple = (trade_date, sw_level)
    if phase_filter:
        phase_clause = 'AND phase = %s'
        params = (trade_date, sw_level, phase_filter)

    sql = f"""
        SELECT sector_code, sector_name, parent_name,
               mom_21, rs_60, vol_ratio,
               composite_score, score_rank,
               phase, is_inflection, inflection_type
        FROM trade_sector_strength_daily
        WHERE trade_date = %s
          AND sw_level = %s
          {phase_clause}
        ORDER BY score_rank ASC
        LIMIT %s
    """
    params = params + (top_n,)

    rows = execute_query(sql, params, env=env)
    sectors = [_clean_row(r) for r in (rows or [])]

    # Inflections (regardless of top_n, show all for the date)
    infl_rows = execute_query(
        """SELECT sector_code, sector_name, parent_name,
                  mom_21, rs_60, vol_ratio,
                  composite_score, score_rank,
                  phase, is_inflection, inflection_type
           FROM trade_sector_strength_daily
           WHERE trade_date = %s AND sw_level = %s AND is_inflection = 1
           ORDER BY score_rank ASC""",
        (trade_date, sw_level),
        env=env,
    )
    inflections = [_clean_row(r) for r in (infl_rows or [])]

    return {
        'trade_date': trade_date,
        'sectors': sectors,
        'inflections': inflections,
    }


def get_latest_picks(
    top_n: int = 15,
    pick_date: Optional[str] = None,
    sector_filter: Optional[str] = None,
    env: str = 'online',
) -> dict:
    """
    Query latest morning picks.

    Args:
        top_n:         number of top picks to return (default 15)
        pick_date:     'YYYY-MM-DD' or None (use most recent)
        sector_filter: filter by sw_level2 sector name, or None for all
        env:           DB environment

    Returns dict:
        {
            'pick_date': str,
            'picks': [
                {
                    'stock_code', 'stock_name',
                    'sw_level1', 'sw_level2',
                    'sector_score', 'sector_rank',
                    'mom_1m', 'mom_3m', 'rsi_14', 'bias_20',
                    'vol_20', 'turnover_20',
                    'pick_score', 'pick_rank'
                },
                ...
            ]
        }
    """
    if pick_date is None:
        rows = execute_query(
            "SELECT MAX(pick_date) AS d FROM trade_morning_picks",
            env=env,
        )
        if not rows or rows[0]['d'] is None:
            return {'pick_date': None, 'picks': []}
        pick_date = str(rows[0]['d'])

    sector_clause = ''
    params: tuple = (pick_date,)
    if sector_filter:
        sector_clause = 'AND sw_level2 = %s'
        params = (pick_date, sector_filter)

    sql = f"""
        SELECT stock_code, stock_name,
               sw_level1, sw_level2,
               sector_score, sector_rank,
               mom_1m, mom_3m, rsi_14, bias_20,
               vol_20, turnover_20,
               pick_score, pick_rank
        FROM trade_morning_picks
        WHERE pick_date = %s
          {sector_clause}
        ORDER BY pick_rank ASC
        LIMIT %s
    """
    params = params + (top_n,)

    rows = execute_query(sql, params, env=env)
    picks = [_clean_row(r) for r in (rows or [])]

    return {
        'pick_date': pick_date,
        'picks': picks,
    }


def _clean_row(row: dict) -> dict:
    """Convert Decimal/date types to JSON-serializable Python types."""
    result = {}
    for k, v in row.items():
        if hasattr(v, 'strftime'):
            result[k] = str(v)
        elif hasattr(v, '__float__') and not isinstance(v, (int, float, bool)):
            # Decimal
            result[k] = float(v)
        else:
            result[k] = v
    return result
