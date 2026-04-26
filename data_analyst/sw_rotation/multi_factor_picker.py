# -*- coding: utf-8 -*-
"""
多因子选股引擎 —— 基于 Top 强势申万二级行业成分股

算法：
  1. 读当日 trade_sector_strength_daily，取 composite_score Top-N 行业
  2. 从 trade_stock_basic 取成分股（sw_level2 IN top_sectors, is_st=0）
  3. 从 trade_stock_basic_factor / trade_stock_extended_factor 加载因子
  4. RSI_14 / BIAS_20 从 trade_stock_daily 现算
  5. 6因子等权综合选股分 → Top 30 写 trade_morning_picks

用法：
  python -m data_analyst.sw_rotation.multi_factor_picker [--date YYYY-MM-DD] [--env online]
"""
import argparse
import logging
import sys
import os
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, execute_many

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════

TOP_SECTOR_N = 10       # take top-N sectors by composite_score
TOP_PICKS_N = 30        # final picks to persist
RSI_PERIOD = 14
MA_PERIOD = 20
DAILY_LOOKBACK_DAYS = 40  # calendar days to fetch for RSI/BIAS calculation


# ══════════════════════════════════════════════════════════════
# Pure calculation functions (testable without DB)
# ══════════════════════════════════════════════════════════════

def rank_norm(series: pd.Series) -> pd.Series:
    """
    Cross-section min-max normalization to [0, 100].
    NaN values propagated.  All-same values -> 50.
    """
    valid = series.dropna()
    if len(valid) == 0:
        return series * np.nan
    if len(valid) == 1:
        return series.where(series.isna(), 50.0)

    mn = valid.min()
    mx = valid.max()
    if mx == mn:
        return series.where(series.isna(), 50.0)
    return (series - mn) / (mx - mn) * 100


def calc_rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """
    Wilder RSI for the last `period` days.
    Returns None if insufficient data.
    """
    arr = close.dropna().values
    n = period + 1
    if len(arr) < n:
        return None

    arr_use = arr[-(period + 1):]
    deltas = np.diff(arr_use)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def calc_bias_20(close: pd.Series) -> Optional[float]:
    """
    BIAS_20 = (close[-1] / MA20 - 1) * 100
    Returns None if insufficient data.
    """
    arr = close.dropna().values
    if len(arr) < MA_PERIOD:
        return None
    ma20 = np.mean(arr[-MA_PERIOD:])
    if ma20 == 0:
        return None
    return float((arr[-1] / ma20 - 1) * 100)


def calc_composite_pick_score(df: pd.DataFrame) -> pd.Series:
    """
    Compute composite pick score from 6 factors (equal weight).

    Positive factors (higher = better):  mom_1m, mom_3m
    Negative factors (lower = better):   rev_5d, vol_20, rsi_14, bias_20

    For negative factors: normalize with reversed direction, i.e.
      norm_neg(x) = 100 - rank_norm(x)

    Returns Series indexed by df.index, values in [0, 100].
    """
    factor_specs = [
        ('mom_1m', '+'),
        ('mom_3m', '+'),
        # reversal_5 in DB = -pct_change(5), 值越大代表近期跌幅越大
        # 反转因子：近期跌幅大 → 应给高分 → '+' 方向
        ('rev_5d', '+'),
        ('vol_20', '-'),
        ('rsi_14', '-'),
        ('bias_20', '-'),
    ]

    normalized = []
    for col, direction in factor_specs:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors='coerce')
        normed = rank_norm(s)
        if direction == '-':
            normed = 100.0 - normed
        normalized.append(normed)

    if not normalized:
        return pd.Series(np.nan, index=df.index)

    stacked = pd.concat(normalized, axis=1)
    score = stacked.mean(axis=1)
    return score


# ══════════════════════════════════════════════════════════════
# DB helpers
# ══════════════════════════════════════════════════════════════

def get_top_sectors(trade_date: date, top_n: int = TOP_SECTOR_N,
                    env: str = 'online') -> list[dict]:
    """
    Return top-N sectors by composite_score for the given trade_date.
    """
    rows = execute_query(
        """SELECT sector_code, sector_name, composite_score, score_rank
           FROM trade_sector_strength_daily
           WHERE trade_date = %s AND sw_level = 2
             AND composite_score IS NOT NULL
           ORDER BY composite_score DESC
           LIMIT %s""",
        (trade_date.strftime('%Y-%m-%d'), top_n),
        env=env,
    )
    return list(rows) if rows else []


def get_sector_stocks(sector_names: list[str], env: str = 'online') -> pd.DataFrame:
    """
    Return non-ST stocks belonging to any of the given sw_level2 sector names.
    """
    if not sector_names:
        return pd.DataFrame()

    placeholders = ','.join(['%s'] * len(sector_names))
    rows = execute_query(
        f"""SELECT stock_code, stock_name, sw_level1, sw_level2
            FROM trade_stock_basic
            WHERE sw_level2 IN ({placeholders})
              AND (is_st IS NULL OR is_st = 0)""",
        tuple(sector_names),
        env=env,
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def load_stock_factors(stock_codes: list[str], trade_date: date,
                       env: str = 'online') -> pd.DataFrame:
    """
    Load pre-computed factors from basic_factor and extended_factor tables.
    Returns DataFrame indexed by stock_code.
    """
    if not stock_codes:
        return pd.DataFrame()

    date_str = trade_date.strftime('%Y-%m-%d')
    placeholders = ','.join(['%s'] * len(stock_codes))

    # Load basic factors (most recent calc_date <= trade_date)
    basic_rows = execute_query(
        f"""SELECT b.stock_code,
                   b.mom_20   AS mom_1m,
                   b.mom_60   AS mom_3m,
                   b.reversal_5 AS rev_5d,
                   b.volatility_20 AS vol_20,
                   b.vol_ratio,
                   b.turnover AS turnover_20
            FROM trade_stock_basic_factor b
            INNER JOIN (
                SELECT stock_code, MAX(calc_date) AS latest_date
                FROM trade_stock_basic_factor
                WHERE stock_code IN ({placeholders})
                  AND calc_date <= %s
                GROUP BY stock_code
            ) sub ON b.stock_code = sub.stock_code
                 AND b.calc_date = sub.latest_date""",
        tuple(stock_codes) + (date_str,),
        env=env,
    )

    basic_df = pd.DataFrame(basic_rows) if basic_rows else pd.DataFrame()
    if not basic_df.empty:
        basic_df = basic_df.set_index('stock_code')

    return basic_df


def load_daily_prices(stock_codes: list[str], trade_date: date,
                      env: str = 'online') -> dict[str, pd.Series]:
    """
    Load recent daily close prices for RSI_14 and BIAS_20 calculation.
    Returns a dict: stock_code -> pd.Series of close prices (ascending date order).
    """
    if not stock_codes:
        return {}

    start_date = (trade_date - timedelta(days=DAILY_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    end_date = trade_date.strftime('%Y-%m-%d')
    placeholders = ','.join(['%s'] * len(stock_codes))

    rows = execute_query(
        f"""SELECT stock_code, trade_date, close_price
            FROM trade_stock_daily
            WHERE stock_code IN ({placeholders})
              AND trade_date BETWEEN %s AND %s
            ORDER BY stock_code, trade_date ASC""",
        tuple(stock_codes) + (start_date, end_date),
        env=env,
    )

    result: dict[str, pd.Series] = {}
    if not rows:
        return result

    tmp = pd.DataFrame(rows)
    for code, grp in tmp.groupby('stock_code'):
        result[code] = grp.set_index('trade_date')['close_price'].astype(float)

    return result


# ══════════════════════════════════════════════════════════════
# Main computation
# ══════════════════════════════════════════════════════════════

def run_daily(trade_date: Optional[date] = None, env: str = 'online') -> int:
    """
    Compute and persist morning picks for trade_date.

    Returns number of rows written.
    """
    if trade_date is None:
        trade_date = date.today()

    trade_date_str = trade_date.strftime('%Y-%m-%d')
    logger.info("[multi_factor_picker] Computing picks for %s", trade_date_str)

    # 1. Get top sectors
    top_sectors = get_top_sectors(trade_date, top_n=TOP_SECTOR_N, env=env)
    if not top_sectors:
        logger.warning("[multi_factor_picker] No sector strength data for %s, aborting",
                       trade_date_str)
        return 0

    sector_names = [s['sector_name'] for s in top_sectors]
    sector_score_map = {s['sector_name']: s['composite_score'] for s in top_sectors}
    sector_rank_map = {s['sector_name']: s['score_rank'] for s in top_sectors}

    logger.info("[multi_factor_picker] Top sectors: %s", sector_names[:5])

    # 2. Get constituent stocks
    stocks_df = get_sector_stocks(sector_names, env=env)
    if stocks_df.empty:
        logger.warning("[multi_factor_picker] No stocks found for top sectors")
        return 0

    stock_codes = stocks_df['stock_code'].tolist()
    logger.info("[multi_factor_picker] Found %d candidate stocks", len(stock_codes))

    # 3. Load pre-computed factors
    factor_df = load_stock_factors(stock_codes, trade_date, env=env)

    # 4. Load daily prices for RSI/BIAS
    price_data = load_daily_prices(stock_codes, trade_date, env=env)

    # 5. Compute RSI_14 and BIAS_20
    rsi_map: dict[str, Optional[float]] = {}
    bias_map: dict[str, Optional[float]] = {}

    for code in stock_codes:
        close_series = price_data.get(code, pd.Series(dtype=float))
        rsi_map[code] = calc_rsi(close_series, period=RSI_PERIOD)
        bias_map[code] = calc_bias_20(close_series)

    # 6. Build factor DataFrame
    stocks_df = stocks_df.set_index('stock_code')

    # Merge pre-computed factors
    if not factor_df.empty:
        stocks_df = stocks_df.join(factor_df, how='left')
    else:
        for col in ['mom_1m', 'mom_3m', 'rev_5d', 'vol_20', 'vol_ratio', 'turnover_20']:
            stocks_df[col] = np.nan

    stocks_df['rsi_14'] = pd.Series(rsi_map)
    stocks_df['bias_20'] = pd.Series(bias_map)

    # 7. Compute composite pick score
    stocks_df['pick_score'] = calc_composite_pick_score(stocks_df)

    # 8. Rank
    stocks_df['pick_rank'] = stocks_df['pick_score'].rank(
        ascending=False, method='min', na_option='bottom').astype('Int64')

    # 9. Take top-N
    top_picks = stocks_df.nsmallest(TOP_PICKS_N, 'pick_rank').copy()

    # 10. Build records for DB
    records = []
    for code, row in top_picks.iterrows():
        sw2 = row.get('sw_level2', '')
        records.append({
            'pick_date': trade_date_str,
            'stock_code': code,
            'stock_name': row.get('stock_name'),
            'sw_level1': row.get('sw_level1'),
            'sw_level2': sw2,
            'sector_score': (float(sector_score_map.get(sw2)) if sector_score_map.get(sw2) is not None else None),
            'sector_rank': (int(sector_rank_map.get(sw2)) if sector_rank_map.get(sw2) is not None else None),
            'mom_1m': _safe_float(row.get('mom_1m')),
            'mom_3m': _safe_float(row.get('mom_3m')),
            'rsi_14': _safe_float(row.get('rsi_14')),
            'bias_20': _safe_float(row.get('bias_20')),
            'vol_20': _safe_float(row.get('vol_20')),
            'turnover_20': _safe_float(row.get('turnover_20')),
            'pick_score': _safe_float(row.get('pick_score')),
            'pick_rank': (int(row['pick_rank']) if not pd.isna(row.get('pick_rank', np.nan)) else None),
        })

    if not records:
        logger.warning("[multi_factor_picker] No picks to write")
        return 0

    # 11. UPSERT to DB
    sql = """
        INSERT INTO trade_morning_picks
            (pick_date, stock_code, stock_name, sw_level1, sw_level2,
             sector_score, sector_rank,
             mom_1m, mom_3m, rsi_14, bias_20, vol_20, turnover_20,
             pick_score, pick_rank)
        VALUES
            (%(pick_date)s, %(stock_code)s, %(stock_name)s, %(sw_level1)s, %(sw_level2)s,
             %(sector_score)s, %(sector_rank)s,
             %(mom_1m)s, %(mom_3m)s, %(rsi_14)s, %(bias_20)s, %(vol_20)s, %(turnover_20)s,
             %(pick_score)s, %(pick_rank)s)
        ON DUPLICATE KEY UPDATE
            stock_name   = VALUES(stock_name),
            sw_level1    = VALUES(sw_level1),
            sw_level2    = VALUES(sw_level2),
            sector_score = VALUES(sector_score),
            sector_rank  = VALUES(sector_rank),
            mom_1m       = VALUES(mom_1m),
            mom_3m       = VALUES(mom_3m),
            rsi_14       = VALUES(rsi_14),
            bias_20      = VALUES(bias_20),
            vol_20       = VALUES(vol_20),
            turnover_20  = VALUES(turnover_20),
            pick_score   = VALUES(pick_score),
            pick_rank    = VALUES(pick_rank)
    """

    execute_many(sql, records, env=env)
    logger.info("[multi_factor_picker] Wrote %d picks for %s", len(records), trade_date_str)
    return len(records)


def _safe_float(val) -> Optional[float]:
    """Convert to float, return None if invalid."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 6)
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    parser = argparse.ArgumentParser(description='Multi-factor morning picks')
    parser.add_argument('--date', default=None,
                        help='Trade date YYYY-MM-DD (default: today)')
    parser.add_argument('--env', default='online',
                        help='DB environment (default: online)')
    args = parser.parse_args()

    trade_dt = (datetime.strptime(args.date, '%Y-%m-%d').date()
                if args.date else date.today())
    n = run_daily(trade_date=trade_dt, env=args.env)
    print(f"Done: {n} picks written for {trade_dt}")
