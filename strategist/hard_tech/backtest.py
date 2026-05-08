# -*- coding: utf-8 -*-
"""
Hard-tech monthly rebalancing backtest with transaction costs.

Reference:
  - strategist/multi_factor/monthly_backtest.py (monthly rebalance loop)
  - strategist/microcap/backtest.py (transaction cost model)

Features:
  - Monthly rebalancing (every 20 trading days)
  - Transaction costs: buy 0.03%, sell 0.13% (commission + stamp tax + slippage)
  - Industry cap: single industry <= 20% of portfolio
  - R&D intensity as entry filter (stocks without rd data also eligible)
  - Benchmark: CSI300

Usage:
    python -m strategist.hard_tech.backtest --start 2024-01-01
"""
import argparse
import logging
import os
import sys
from datetime import date, timedelta
from time import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, get_connection
from strategist.multi_factor.scorer import FactorSelector
from strategist.multi_factor.data_loader import load_stock_filter, _read_sql_by_batches

from .config import (
    STRATEGY_FACTOR_GROUPS, STRATEGY_FACTOR_DIRECTIONS,
    BACKTEST_PARAMS, HARD_TECH_INDUSTRIES, RD_INTENSITY_THRESHOLD,
)
from .stock_pool import build_hardtech_universe, get_industry_map, get_stock_names
from .data_loader import _read_sql_by_batches as _read_batches_ht

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(ROOT, 'output', 'hard_tech')


def get_monthly_dates(start_date: str, end_date: str) -> list:
    """Get first available factor date per month."""
    conn = get_connection()
    try:
        df = pd.read_sql(
            f"SELECT DISTINCT calc_date FROM trade_stock_valuation_factor "
            f"WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}' "
            f"ORDER BY calc_date",
            conn
        )
    finally:
        conn.close()

    if df.empty:
        return []

    dates = pd.to_datetime(df.iloc[:, 0])
    ym = pd.Series(dates, name='date').dt.to_period('M')
    monthly = dates.groupby(ym).min().tolist()
    logger.info(f"Monthly dates: {len(monthly)} months from {monthly[0].strftime('%Y-%m-%d')} to {monthly[-1].strftime('%Y-%m-%d')}")
    return monthly


def load_backtest_data(start_date: str, end_date: str, monthly_dates: list):
    """
    Load factor panel + close prices for backtest.

    Returns:
        panel: DataFrame with MultiIndex (trade_date, stock_code)
        prices: DataFrame with MultiIndex (trade_date, stock_code), column close_price
    """
    dates_str = [d.strftime('%Y-%m-%d') for d in monthly_dates]

    # Load factors for monthly dates
    sql_ext = (
        "SELECT stock_code, calc_date AS trade_date, "
        "revenue_growth, gross_margin, roe_ttm "
        "FROM trade_stock_extended_factor "
        "WHERE calc_date = '__trade_date__'"
    )
    df_ext = _read_batches_ht(sql_ext, 'trade_date', dates_str)

    sql_basic = (
        "SELECT stock_code, calc_date AS trade_date, mom_20 "
        "FROM trade_stock_basic_factor "
        "WHERE calc_date = '__trade_date__'"
    )
    df_basic = _read_batches_ht(sql_basic, 'trade_date', dates_str)

    sql_val = (
        "SELECT stock_code, calc_date AS trade_date, market_cap "
        "FROM trade_stock_valuation_factor "
        "WHERE calc_date = '__trade_date__'"
    )
    df_val = _read_batches_ht(sql_val, 'trade_date', dates_str)

    sql_hardtech = (
        "SELECT stock_code, calc_date AS trade_date, "
        "rd_intensity, rd_growth "
        "FROM trade_stock_hardtech_factor "
        "WHERE calc_date = '__trade_date__'"
    )
    df_ht = _read_batches_ht(sql_hardtech, 'trade_date', dates_str)

    dfs = [df for df in [df_ext, df_basic, df_val, df_ht] if not df.empty]
    if not dfs:
        return pd.DataFrame(), pd.DataFrame()

    for df in dfs:
        for col in df.columns:
            if col not in ('stock_code', 'trade_date'):
                df[col] = pd.to_numeric(df[col], errors='coerce')

    result = dfs[0]
    for other in dfs[1:]:
        result = pd.merge(result, other, on=['trade_date', 'stock_code'], how='outer')

    result['trade_date'] = pd.to_datetime(result['trade_date'])
    panel = result.set_index(['trade_date', 'stock_code']).sort_index()
    logger.info(f"Factor panel: {len(panel):,} rows")

    # Load prices: need both rebalance dates and the dates between them
    # Load all trading dates in range
    conn = get_connection()
    try:
        all_dates_df = pd.read_sql(
            f"SELECT DISTINCT trade_date FROM trade_stock_daily "
            f"WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}' "
            f"ORDER BY trade_date",
            conn
        )
    finally:
        conn.close()

    if all_dates_df.empty:
        return panel, pd.DataFrame()

    all_dates = [str(d) for d in all_dates_df.iloc[:, 0]]

    # Load prices in chunks of 5 dates
    sql_price = (
        "SELECT stock_code, trade_date, close_price "
        "FROM trade_stock_daily "
        "WHERE trade_date = '__trade_date__'"
    )
    prices = _read_batches_ht(sql_price, 'trade_date', all_dates)

    if not prices.empty:
        prices['trade_date'] = pd.to_datetime(prices['trade_date'])
        prices['close_price'] = pd.to_numeric(prices['close_price'], errors='coerce')
        prices = prices.set_index(['trade_date', 'stock_code']).sort_index()
    logger.info(f"Prices: {len(prices):,} rows")

    return panel, prices


def load_benchmark(start_date: str, end_date: str) -> pd.Series:
    """Load CSI300 close prices as benchmark."""
    code = BACKTEST_PARAMS['benchmark_code']
    sql = f"""
        SELECT trade_date, close_price
        FROM trade_stock_daily
        WHERE stock_code = '{code}'
          AND trade_date >= '{start_date}' AND trade_date <= '{end_date}'
        ORDER BY trade_date
    """
    rows = execute_query(sql)
    if not rows:
        logger.warning(f"No benchmark data for {code}")
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
    return df.set_index('trade_date')['close_price']


def build_selector() -> FactorSelector:
    """Build FactorSelector with IC-validated hard-tech factor groups."""
    return FactorSelector(
        use_groups=True,
        factor_groups=STRATEGY_FACTOR_GROUPS,
        factor_directions=STRATEGY_FACTOR_DIRECTIONS,
    )


def mark_rd_eligible(panel: pd.DataFrame, threshold: float = None) -> pd.DataFrame:
    """
    Add rd_eligible column to panel.

    rd_eligible = True if:
      - rd_intensity >= threshold (strong hard-tech)
      - OR rd_intensity is NULL (no data, but still eligible -- may be missed gems)

    This ensures stocks without rd data are not excluded from the strategy.
    """
    if threshold is None:
        threshold = RD_INTENSITY_THRESHOLD

    if 'rd_intensity' not in panel.columns:
        panel['rd_eligible'] = True
        return panel

    panel['rd_eligible'] = (
        panel['rd_intensity'].isna() |          # no rd data -> eligible
        (panel['rd_intensity'] >= threshold)     # high rd -> eligible
    )
    n_with_rd = panel['rd_intensity'].notna().sum()
    n_eligible = panel['rd_eligible'].sum()
    logger.info(f"RD eligibility: {n_eligible} eligible ({n_with_rd} with rd data, threshold={threshold:.1%})")
    return panel


def backtest(start_date: str, end_date: str = None, top_n: int = None):
    """
    Run monthly rebalancing backtest with transaction costs.

    Args:
        start_date: backtest start (YYYY-MM-DD)
        end_date: backtest end (default today)
        top_n: stocks per rebalance (default from config)

    Returns:
        DataFrame with monthly results + summary stats
    """
    if end_date is None:
        end_date = date.today().strftime('%Y-%m-%d')
    if top_n is None:
        top_n = BACKTEST_PARAMS['top_n']

    params = BACKTEST_PARAMS
    buy_cost = params['buy_cost_rate']
    sell_cost = params['sell_cost_rate']

    logger.info(f"Starting backtest: {start_date} ~ {end_date}, top_n={top_n}")

    # Load data
    t0 = time()
    monthly_dates = get_monthly_dates(start_date, end_date)
    if not monthly_dates:
        logger.error("No monthly dates found")
        return pd.DataFrame()

    panel, prices = load_backtest_data(start_date, end_date, monthly_dates)
    benchmark = load_benchmark(start_date, end_date)

    if panel.empty:
        logger.error("No factor data loaded")
        return pd.DataFrame()

    # Build helpers
    selector = build_selector()
    industry_map = get_industry_map()
    blacklist = load_stock_filter()
    panel = mark_rd_eligible(panel)

    logger.info(f"Data loaded in {time()-t0:.1f}s")

    # Monthly rebalancing loop
    results = []
    for i, dt in enumerate(monthly_dates):
        sell_dt = monthly_dates[i + 1] if i + 1 < len(monthly_dates) else None

        try:
            df_day = panel.loc[dt]
        except KeyError:
            continue
        if isinstance(df_day, pd.Series):
            continue

        # Filter to hard-tech universe + rd eligible
        df_day = df_day[df_day['rd_eligible']] if 'rd_eligible' in df_day.columns else df_day
        if df_day.empty:
            continue

        # Select top N
        top_stocks = selector.select_top_n(
            df_day, top_n=top_n,
            blacklist=blacklist,
            industry_map=industry_map,
        )
        if not top_stocks:
            continue

        # Calculate returns with transaction costs
        stock_returns = []
        for code in top_stocks:
            try:
                buy_price = float(prices.loc[(dt, code), 'close_price'])
            except (KeyError, TypeError, ValueError):
                continue
            if buy_price <= 0 or np.isnan(buy_price):
                continue

            if sell_dt is not None:
                try:
                    sell_price = float(prices.loc[(sell_dt, code), 'close_price'])
                except (KeyError, TypeError, ValueError):
                    continue
                if sell_price <= 0 or np.isnan(sell_price):
                    continue

                # Return after transaction costs
                cost_adj_buy = buy_price * (1 + buy_cost)
                cost_adj_sell = sell_price * (1 - sell_cost)
                ret = cost_adj_sell / cost_adj_buy - 1
                stock_returns.append(ret)

        port_ret = np.mean(stock_returns) if stock_returns else 0.0

        # Benchmark return
        bm_ret = 0.0
        if sell_dt is not None and not benchmark.empty:
            try:
                bm_buy = float(benchmark.loc[dt])
                bm_sell = float(benchmark.loc[sell_dt])
                if bm_buy > 0:
                    bm_ret = bm_sell / bm_buy - 1
            except (KeyError, TypeError):
                pass

        results.append({
            'rebalance_date': dt,
            'sell_date': sell_dt,
            'month': dt.strftime('%Y-%m'),
            'n_stocks': len(top_stocks),
            'n_with_returns': len(stock_returns),
            'portfolio_return': port_ret,
            'benchmark_return': bm_ret,
            'excess_return': port_ret - bm_ret,
            'top_stocks': top_stocks,
        })

    if not results:
        logger.error("No backtest results")
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df['cum_strat'] = (1 + df['portfolio_return']).cumprod() - 1
    df['cum_bm'] = (1 + df['benchmark_return']).cumprod() - 1
    df['cum_excess'] = (1 + df['excess_return']).cumprod() - 1

    return df


def print_report(results: pd.DataFrame):
    """Print backtest report."""
    if results.empty:
        print("No results to report")
        return

    n = len(results)
    print("\n" + "=" * 90)
    print("Hard-Tech Strategy Backtest Report")
    print("=" * 90)

    # Monthly returns table
    print(f"\n| Month | N | Portfolio | Benchmark | Excess | CumStrat | CumBM |")
    print(f"|-------|---|-----------|-----------|--------|----------|-------|")

    for _, row in results.iterrows():
        mark = ' *' if row['excess_return'] > 0 else ''
        pr = f"{row['portfolio_return']:+.2%}" if not np.isnan(row['portfolio_return']) else '-'
        br = f"{row['benchmark_return']:+.2%}" if not np.isnan(row['benchmark_return']) else '-'
        er = f"{row['excess_return']:+.2%}" if not np.isnan(row['excess_return']) else '-'
        cs = f"{row['cum_strat']:+.2%}" if not np.isnan(row['cum_strat']) else '-'
        cb = f"{row['cum_bm']:+.2%}" if not np.isnan(row['cum_bm']) else '-'
        print(f"| {row['month']} | {row['n_stocks']} | {pr} | {br} | {er} | {cs} | {cb} |{mark}")

    # Summary
    total_strat = (1 + results['portfolio_return']).prod() - 1
    total_bm = (1 + results['benchmark_return']).prod() - 1
    total_excess = total_strat - total_bm

    excess = results['excess_return']
    avg_excess = excess.mean()
    std_excess = excess.std()
    win_rate = (excess > 0).mean()
    sharpe = avg_excess / std_excess * np.sqrt(12) if std_excess > 0 else 0

    cum_exc = (1 + excess).cumprod()
    peak = cum_exc.cummax()
    dd_series = (cum_exc - peak) / peak
    max_dd = dd_series.min()

    strat_ret = results['portfolio_return']
    ann_ret = (1 + total_strat) ** (12 / n) - 1 if n > 0 else 0
    ann_vol = strat_ret.std() * np.sqrt(12)

    best_idx = excess.idxmax()
    worst_idx = excess.idxmin()

    print(f"\n### Summary ({n} months)\n")
    print(f"| Metric | Value |")
    print(f"|--------|-------|")
    print(f"| Total Return (Strategy) | {total_strat:.2%} |")
    print(f"| Total Return (Benchmark) | {total_bm:.2%} |")
    print(f"| Total Excess | {total_excess:+.2%} |")
    print(f"| Annualized Return | {ann_ret:.2%} |")
    print(f"| Annualized Volatility | {ann_vol:.2%} |")
    print(f"| Sharpe Ratio (ann.) | {sharpe:.2f} |")
    print(f"| Win Rate (excess > 0) | {win_rate:.0%} |")
    print(f"| Max Drawdown (excess) | {max_dd:.2%} |")
    print(f"| Best Month | {results.loc[best_idx, 'month']}: {excess[best_idx]:+.2%} |")
    print(f"| Worst Month | {results.loc[worst_idx, 'month']}: {excess[worst_idx]:+.2%} |")

    # Show latest holdings
    if not results.empty:
        last = results.iloc[-1]
        codes = last.get('top_stocks', [])
        if codes:
            names = get_stock_names(codes)
            print(f"\n### Latest Holdings ({last['month']})\n")
            for j, code in enumerate(codes[:10], 1):
                print(f"  {j}. {code} {names.get(code, '')}")

    # Save to file
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    save_path = os.path.join(OUTPUT_DIR, 'backtest_results.csv')
    save_df = results.drop(columns=['top_stocks'], errors='ignore')
    save_df.to_csv(save_path, index=False)
    logger.info(f"Results saved to {save_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hard-Tech Backtest')
    parser.add_argument('--start', type=str, default='2024-01-01')
    parser.add_argument('--end', type=str, default=None)
    parser.add_argument('--top-n', type=int, default=None)
    args = parser.parse_args()

    results = backtest(args.start, args.end, args.top_n)
    print_report(results)
