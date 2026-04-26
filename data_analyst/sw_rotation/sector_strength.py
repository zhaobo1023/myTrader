# -*- coding: utf-8 -*-
"""
申万二级行业每日强度计算

指标：
  MOM_21    = (close[-1] / close[-22] - 1) * 100
  RS_60     = 60日收益截面排名分位 (0-100)
  VOL_RATIO = mean(amount[-10:]) / mean(amount[-60:])  成交额量比

综合分：
  composite_score = 0.4 * rank_norm(MOM_21) + 0.3 * RS_60 + 0.3 * rank_norm(VOL_RATIO)

四象限相位：accel_up / decel_up / accel_down / decel_down / neutral

用法：
  python -m data_analyst.sw_rotation.sector_strength [--date YYYY-MM-DD] [--env online]
"""
import argparse
import logging
import sys
import os
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

# Project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, execute_many

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════

LOOKBACK_DAYS = 120     # calendar days to fetch (covers ~80 trading days)
MOM_WINDOW = 21         # 21-day momentum
RS_WINDOW = 60          # 60-day relative-strength cross-section
VOL_SHORT = 10          # short vol window (days)
VOL_LONG = 60           # long vol window (days)


# ══════════════════════════════════════════════════════════════
# Pure calculation functions (testable without DB / network)
# ══════════════════════════════════════════════════════════════

def rank_norm(series: pd.Series) -> pd.Series:
    """
    Cross-section min-max normalization to [0, 100].

    Handles all-same values (returns 50) and NaN (propagated).
    """
    valid = series.dropna()
    if len(valid) == 0:
        return series * np.nan
    if len(valid) == 1:
        return series.fillna(np.nan).where(series.isna(), 50.0)

    mn = valid.min()
    mx = valid.max()
    if mx == mn:
        # all values identical -> mid-point
        return series.where(series.isna(), 50.0)
    return (series - mn) / (mx - mn) * 100


def calc_mom_21(close: pd.Series) -> Optional[float]:
    """21-day momentum: (close[-1] / close[-22] - 1) * 100."""
    arr = close.dropna().values
    if len(arr) < 22:
        return None
    return float((arr[-1] / arr[-22] - 1) * 100)


def calc_rs_60_cross(ret_60: pd.Series) -> pd.Series:
    """
    Cross-section rank of 60-day return in [0, 100].

    ret_60: Series indexed by sector_code, values = 60d returns.
    """
    valid = ret_60.dropna()
    if len(valid) == 0:
        return ret_60 * np.nan
    ranks = valid.rank(method='average', na_option='keep', pct=True) * 100
    return ranks.reindex(ret_60.index)


def calc_vol_ratio(amount: pd.Series) -> Optional[float]:
    """
    Volume (amount) ratio: mean of last VOL_SHORT days / mean of last VOL_LONG days.

    amount: time-ordered Series of daily trading amount values.
    """
    arr = amount.dropna().values
    if len(arr) < VOL_LONG:
        return None
    short_mean = np.mean(arr[-VOL_SHORT:])
    long_mean = np.mean(arr[-VOL_LONG:])
    if long_mean == 0:
        return None
    return float(short_mean / long_mean)


def calc_composite_score(
    mom_21_series: pd.Series,
    rs_60_series: pd.Series,
    vol_ratio_series: pd.Series,
) -> pd.Series:
    """
    composite_score = 0.4 * rank_norm(MOM_21) + 0.3 * RS_60 + 0.3 * rank_norm(VOL_RATIO)

    All inputs are Series indexed by sector_code.
    """
    norm_mom = rank_norm(mom_21_series)
    norm_vol = rank_norm(vol_ratio_series)

    score = 0.4 * norm_mom + 0.3 * rs_60_series + 0.3 * norm_vol
    return score


def calc_phase(mom_21_today: Optional[float], mom_21_yesterday: Optional[float]) -> str:
    """
    Four-quadrant phase classification.

    Rules:
      |mom_21| < 0.5 -> neutral
      mom > 0 and delta > 0  -> accel_up
      mom > 0 and delta <= 0 -> decel_up
      mom < 0 and delta < 0  -> accel_down
      mom < 0 and delta >= 0 -> decel_down
    """
    if mom_21_today is None:
        return 'neutral'
    if abs(mom_21_today) < 0.5:
        return 'neutral'
    if mom_21_yesterday is None:
        return 'neutral'
    delta = mom_21_today - mom_21_yesterday
    if mom_21_today > 0:
        return 'accel_up' if delta > 0 else 'decel_up'
    else:  # mom_21_today < 0
        # delta == 0（动量持平）也归为 decel_down，表示下跌动能尚未消退
        return 'accel_down' if delta < 0 else 'decel_down'


def detect_inflection(phase_today: str, phase_yesterday: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Detect phase inflection points.

    turn_up:   yesterday in {decel_down, neutral} AND today in {accel_up, decel_up}
    turn_down: yesterday in {decel_up, neutral}   AND today in {accel_down, decel_down}

    Returns (is_inflection: bool, inflection_type: str | None)
    """
    if phase_yesterday is None:
        return False, None

    up_phases = {'accel_up', 'decel_up'}
    down_phases = {'accel_down', 'decel_down'}
    turn_up_from = {'decel_down', 'neutral'}
    turn_down_from = {'decel_up', 'neutral'}

    if phase_today in up_phases and phase_yesterday in turn_up_from:
        return True, 'turn_up'
    if phase_today in down_phases and phase_yesterday in turn_down_from:
        return True, 'turn_down'
    return False, None


# ══════════════════════════════════════════════════════════════
# Data fetching — from DB (aggregate stock-level data by sector)
# ══════════════════════════════════════════════════════════════

def fetch_level2_price_data(start_date: str, end_date: str,
                            env: str = 'online') -> dict[str, pd.DataFrame]:
    """
    Build SW level-2 industry daily "index" from individual stock data in DB.

    For each sector, we compute a daily equal-weight average close price and
    sum of amount across constituent stocks.  This avoids depending on external
    AKShare/Eastmoney APIs that are frequently broken or blocked.

    Returns dict: sector_name -> DataFrame with columns [trade_date, close, amount]
                  sorted ascending by trade_date.
                  attrs: sector_name, parent_name
    """
    logger.info("Fetching sector price data from DB (aggregated from stock-level)...")

    # 1. Get sector classification: sw_level2 -> sw_level1 mapping
    cls_rows = execute_query(
        """SELECT sw_level1, sw_level2, COUNT(*) AS cnt
           FROM trade_stock_basic
           WHERE sw_level2 IS NOT NULL AND sw_level2 != ''
             AND (is_st IS NULL OR is_st = 0)
           GROUP BY sw_level1, sw_level2
           HAVING cnt >= 3""",
        env=env,
    )
    if not cls_rows:
        logger.warning("No SW classification data in trade_stock_basic")
        return {}

    sector_parent: dict[str, str] = {}
    for r in cls_rows:
        sector_parent[r['sw_level2']] = r['sw_level1'] or ''

    sector_names = list(sector_parent.keys())
    logger.info("Found %d level-2 sectors with >= 3 stocks", len(sector_names))

    # 2. Fetch daily aggregated data: equal-weight avg close + sum amount
    placeholders = ','.join(['%s'] * len(sector_names))
    agg_rows = execute_query(
        f"""SELECT b.sw_level2 AS sector_name,
                   d.trade_date,
                   AVG(d.close_price) AS close,
                   SUM(d.amount)      AS amount
            FROM trade_stock_daily d
            JOIN trade_stock_basic b ON d.stock_code = b.stock_code
            WHERE d.trade_date BETWEEN %s AND %s
              AND b.sw_level2 IN ({placeholders})
              AND (b.is_st IS NULL OR b.is_st = 0)
            GROUP BY b.sw_level2, d.trade_date
            ORDER BY b.sw_level2, d.trade_date ASC""",
        (start_date, end_date) + tuple(sector_names),
        env=env,
    )

    if not agg_rows:
        logger.warning("No aggregated data returned from DB")
        return {}

    # 3. Build per-sector DataFrames
    agg_df = pd.DataFrame(agg_rows)
    agg_df['close'] = pd.to_numeric(agg_df['close'], errors='coerce')
    agg_df['amount'] = pd.to_numeric(agg_df['amount'], errors='coerce')

    result: dict[str, pd.DataFrame] = {}
    for sector_name, grp in agg_df.groupby('sector_name'):
        sub = grp[['trade_date', 'close', 'amount']].copy().sort_values('trade_date')
        sub.attrs['sector_name'] = sector_name
        sub.attrs['parent_name'] = sector_parent.get(sector_name, '')
        # Use sector_name as key (we no longer have sector_code from AKShare)
        result[sector_name] = sub

    logger.info("Built aggregated data for %d level-2 sectors", len(result))
    return result


# ══════════════════════════════════════════════════════════════
# Yesterday phase lookup (from DB)
# ══════════════════════════════════════════════════════════════

def _get_yesterday_data(trade_date: date, env: str = 'online') -> tuple[dict[str, str], dict[str, float]]:
    """
    Load phase and mom_21 from the most recent trading day before trade_date.

    Uses a subquery to pin the exact previous date, avoiding LIMIT-based
    fragility when there are >500 total rows across multiple dates.

    Returns dicts keyed by sector_name (not sector_code).
    """
    rows = execute_query(
        """SELECT sector_name, phase, mom_21
           FROM trade_sector_strength_daily
           WHERE trade_date = (
               SELECT MAX(trade_date)
               FROM trade_sector_strength_daily
               WHERE trade_date < %s AND sw_level = 2
           ) AND sw_level = 2""",
        (trade_date.strftime('%Y-%m-%d'),),
        env=env,
    )
    phases: dict[str, str] = {}
    mom21s: dict[str, float] = {}
    for r in (rows or []):
        name = r['sector_name']
        phases[name] = r['phase'] or 'neutral'
        if r['mom_21'] is not None:
            mom21s[name] = float(r['mom_21'])
    return phases, mom21s


# ══════════════════════════════════════════════════════════════
# Main computation
# ══════════════════════════════════════════════════════════════

def run_daily(trade_date: Optional[date] = None, env: str = 'online') -> int:
    """
    Compute and persist SW level-2 industry strength for trade_date.

    Returns number of rows written.
    """
    if trade_date is None:
        trade_date = date.today()

    end_date = trade_date.strftime('%Y-%m-%d')
    start_date = (trade_date - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')

    logger.info("[sector_strength] Computing for %s (lookback from %s)", end_date, start_date)

    # Fetch price data (aggregated from stock-level in DB)
    price_data = fetch_level2_price_data(start_date, end_date, env=env)
    if not price_data:
        logger.warning("[sector_strength] No price data fetched, aborting")
        return 0

    # Load previous day's phase + mom_21 in one query
    yesterday_phases, yesterday_mom21 = _get_yesterday_data(trade_date, env=env)

    # Build per-sector metrics
    records: list[dict] = []
    mom_21_map: dict[str, Optional[float]] = {}
    vol_ratio_map: dict[str, Optional[float]] = {}

    # Also need 60-day return for RS cross-section
    ret_60_map: dict[str, Optional[float]] = {}

    for key, df in price_data.items():
        df_sorted = df.sort_values('trade_date')
        close = df_sorted['close'].dropna()
        amount = df_sorted['amount']

        mom = calc_mom_21(close)
        vr = calc_vol_ratio(amount)

        mom_21_map[key] = mom
        vol_ratio_map[key] = vr

        # 60-day return for RS cross-section
        arr = close.values
        if len(arr) >= 61:
            ret_60_map[key] = float((arr[-1] / arr[-61] - 1) * 100)
        else:
            ret_60_map[key] = None

    # Cross-section RS_60
    ret_60_series = pd.Series(ret_60_map)
    rs_60_series = calc_rs_60_cross(ret_60_series)

    # Composite score
    mom_series = pd.Series(mom_21_map)
    vol_series = pd.Series(vol_ratio_map)
    composite_series = calc_composite_score(mom_series, rs_60_series, vol_series)

    # Score rank (ascending rank = 1 is weakest)
    rank_series = composite_series.rank(ascending=False, method='min', na_option='bottom')

    # Build rows for DB write
    trade_date_str = trade_date.strftime('%Y-%m-%d')

    for key, df in price_data.items():
        sector_name = df.attrs.get('sector_name', key)
        parent_name = df.attrs.get('parent_name', None) or None

        mom21 = mom_21_map.get(key)
        vr = vol_ratio_map.get(key)
        rs60 = rs_60_series.get(key) if not pd.isna(rs_60_series.get(key, np.nan)) else None
        comp = composite_series.get(key) if not pd.isna(composite_series.get(key, np.nan)) else None
        rank = int(rank_series.get(key)) if not pd.isna(rank_series.get(key, np.nan)) else None

        # Phase (keyed by sector_name now)
        prev_mom = yesterday_mom21.get(sector_name)
        phase = calc_phase(mom21, prev_mom)

        # Inflection
        prev_phase = yesterday_phases.get(sector_name)
        is_infl, infl_type = detect_inflection(phase, prev_phase)

        records.append({
            'trade_date': trade_date_str,
            'sw_level': 2,
            'sector_code': sector_name,  # use name as code (no AKShare codes)
            'sector_name': sector_name,
            'parent_name': parent_name,
            'mom_21': round(mom21, 4) if mom21 is not None else None,
            'rs_60': round(rs60, 4) if rs60 is not None else None,
            'vol_ratio': round(vr, 4) if vr is not None else None,
            'composite_score': round(comp, 4) if comp is not None else None,
            'score_rank': rank,
            'phase': phase,
            'is_inflection': 1 if is_infl else 0,
            'inflection_type': infl_type,
            'hist_short': None,  # optional; skip for now
            'hist_long': None,
        })

    if not records:
        logger.warning("[sector_strength] No records computed")
        return 0

    # UPSERT to DB
    sql = """
        INSERT INTO trade_sector_strength_daily
            (trade_date, sw_level, sector_code, sector_name, parent_name,
             mom_21, rs_60, vol_ratio, composite_score, score_rank,
             phase, is_inflection, inflection_type, hist_short, hist_long)
        VALUES
            (%(trade_date)s, %(sw_level)s, %(sector_code)s, %(sector_name)s, %(parent_name)s,
             %(mom_21)s, %(rs_60)s, %(vol_ratio)s, %(composite_score)s, %(score_rank)s,
             %(phase)s, %(is_inflection)s, %(inflection_type)s, %(hist_short)s, %(hist_long)s)
        ON DUPLICATE KEY UPDATE
            sector_name     = VALUES(sector_name),
            parent_name     = VALUES(parent_name),
            mom_21          = VALUES(mom_21),
            rs_60           = VALUES(rs_60),
            vol_ratio       = VALUES(vol_ratio),
            composite_score = VALUES(composite_score),
            score_rank      = VALUES(score_rank),
            phase           = VALUES(phase),
            is_inflection   = VALUES(is_inflection),
            inflection_type = VALUES(inflection_type),
            hist_short      = VALUES(hist_short),
            hist_long       = VALUES(hist_long)
    """

    execute_many(sql, records, env=env)
    logger.info("[sector_strength] Wrote %d records for %s", len(records), trade_date_str)
    return len(records)


# ══════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    parser = argparse.ArgumentParser(description='Compute SW level-2 sector strength')
    parser.add_argument('--date', default=None,
                        help='Trade date YYYY-MM-DD (default: today)')
    parser.add_argument('--env', default='online',
                        help='DB environment (default: online)')
    args = parser.parse_args()

    trade_dt = (datetime.strptime(args.date, '%Y-%m-%d').date()
                if args.date else date.today())
    n = run_daily(trade_date=trade_dt, env=args.env)
    print(f"Done: {n} sector records written for {trade_dt}")
