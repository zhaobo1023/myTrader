# -*- coding: utf-8 -*-
"""
Monthly rebalancing backtest with regime analysis.

Plan A: Unconditional monthly rebalancing (every month)
Plan B: Conditional (only activate in low risk appetite environments)

Data:
  - Factor panel from 3 factor tables (loaded for monthly dates only)
  - Close prices from trade_stock_daily
  - Market benchmark: equal-weight index of top-100 market cap stocks
  - Regime indicators: cross-sectional volatility, market momentum, drawdown

Usage:
    python -m strategist.multi_factor.monthly_backtest
    python -m strategist.multi_factor.monthly_backtest --start 2024-01-01 --end 2026-03-31
    python -m strategist.multi_factor.monthly_backtest --plan a --top-n 30
    python -m strategist.multi_factor.monthly_backtest --plan b
"""

import argparse
import logging
import os
import sys
from datetime import timedelta
from time import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import get_connection, execute_query
from strategist.multi_factor.config import DEFAULT_TOP_N
from strategist.multi_factor.data_loader import (
    load_stock_filter, load_industry_map,
    _read_sql_by_batches, _add_composite_factors,
)
from strategist.multi_factor.scorer import FactorSelector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(ROOT, 'output', 'multi_factor')


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def get_monthly_factor_dates(start_date: str, end_date: str) -> list:
    """Get the first available factor date for each month in range."""
    logger.info(f"Querying available factor dates: {start_date} ~ {end_date}")
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
        logger.error("No factor dates found")
        return []

    dates = pd.to_datetime(df.iloc[:, 0])
    dates_series = pd.Series(dates, name='date')
    ym = dates_series.dt.to_period('M')
    monthly_dates = dates_series.groupby(ym).min().tolist()

    logger.info(f"Found {len(dates)} factor dates, {len(monthly_dates)} monthly starts")
    for dt in monthly_dates:
        logger.info(f"  {dt.strftime('%Y-%m-%d')}")

    return monthly_dates


def load_factor_for_dates(dates: list) -> pd.DataFrame:
    """Load factor panel only for specific dates (not the whole range)."""
    if not dates:
        return pd.DataFrame()

    dates_str = [d.strftime('%Y-%m-%d') for d in dates]
    logger.info(f"Loading factor data for {len(dates_str)} monthly dates...")

    t0 = time()

    sql_val = (
        "SELECT stock_code, calc_date AS trade_date, pb, pe_ttm, market_cap "
        "FROM trade_stock_valuation_factor "
        "WHERE calc_date = '__trade_date__'"
    )
    df_val = _read_sql_by_batches(sql_val, 'trade_date', dates_str)
    logger.info(f"  valuation_factor: {len(df_val):,} rows")

    sql_basic = (
        "SELECT stock_code, calc_date AS trade_date, volatility_20, close "
        "FROM trade_stock_basic_factor "
        "WHERE calc_date = '__trade_date__'"
    )
    df_basic = _read_sql_by_batches(sql_basic, 'trade_date', dates_str)
    logger.info(f"  basic_factor: {len(df_basic):,} rows")

    sql_ext = (
        "SELECT stock_code, calc_date AS trade_date, roe_ttm "
        "FROM trade_stock_extended_factor "
        "WHERE calc_date = '__trade_date__'"
    )
    df_ext = _read_sql_by_batches(sql_ext, 'trade_date', dates_str)
    logger.info(f"  extended_factor: {len(df_ext):,} rows")

    dfs = [df for df in [df_val, df_basic, df_ext] if not df.empty]
    if not dfs:
        return pd.DataFrame()

    result = dfs[0]
    for other in dfs[1:]:
        result = pd.merge(result, other, on=['trade_date', 'stock_code'], how='outer')

    result['trade_date'] = pd.to_datetime(result['trade_date'])
    for col in result.columns:
        if col not in ('stock_code', 'trade_date'):
            result[col] = pd.to_numeric(result[col], errors='coerce')

    result = result.set_index(['trade_date', 'stock_code']).sort_index()
    _add_composite_factors(result)

    logger.info(f"Factor panel loaded in {time()-t0:.1f}s: {len(result):,} rows")
    return result


def load_prices_for_dates(dates: list) -> pd.DataFrame:
    """
    Load close prices from trade_stock_daily for specific dates.

    Batches dates into groups of 5 to reduce number of queries vs per-date,
    while keeping result sets manageable for remote DB.
    """
    if not dates:
        return pd.DataFrame()

    dates_str = [d.strftime('%Y-%m-%d') for d in dates]
    logger.info(f"Loading prices for {len(dates_str)} dates...")

    t0 = time()
    all_dfs = []

    # Group dates into batches of 5
    BATCH = 5
    for i in range(0, len(dates_str), BATCH):
        batch = dates_str[i:i + BATCH]
        date_list = "','".join(batch)
        for attempt in range(3):
            try:
                conn = get_connection()
                try:
                    sql = (
                        f"SELECT stock_code, trade_date, close_price "
                        f"FROM trade_stock_daily "
                        f"WHERE trade_date IN ('{date_list}')"
                    )
                    df_chunk = pd.read_sql(sql, conn)
                finally:
                    conn.close()
                if not df_chunk.empty:
                    all_dfs.append(df_chunk)
                break
            except Exception as e:
                wait = 10 * (attempt + 1)
                logger.warning(f"  retry {attempt+1}: {e}, wait {wait}s")
                if attempt < 2:
                    import time as _time
                    _time.sleep(wait)
                else:
                    logger.error(f"  failed batch starting {batch[0]}: {e}")

    if not all_dfs:
        return pd.DataFrame()

    df = pd.concat(all_dfs, ignore_index=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
    df = df.set_index(['trade_date', 'stock_code']).sort_index()

    logger.info(f"Prices loaded in {time()-t0:.1f}s: {len(df):,} rows")
    return df


def load_market_index(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Build a market-cap-weighted index from top-100 stocks as benchmark.
    Also computes cross-sectional daily return volatility as regime proxy.

    Uses bulk SQL by month chunks instead of per-date queries (much faster
    for remote DB with ~622 trading days).
    """
    logger.info(f"Loading market index: {start_date} ~ {end_date}")

    # 1. Get top 100 stocks by latest market cap
    conn = get_connection()
    try:
        df_mc = pd.read_sql(
            "SELECT stock_code FROM trade_stock_valuation_factor "
            "WHERE calc_date = (SELECT MAX(calc_date) FROM trade_stock_valuation_factor) "
            "ORDER BY market_cap DESC LIMIT 100",
            conn
        )
    finally:
        conn.close()

    if df_mc.empty:
        logger.error("Cannot determine top-100 stocks for benchmark")
        return pd.DataFrame()

    top_codes = df_mc['stock_code'].tolist()
    logger.info(f"  top-100 stocks for benchmark (latest MC)")

    # 2. Bulk load: single query with date range + stock filter
    # Split into ~3-month chunks to avoid timeout on large result sets
    t0 = time()
    code_list = "','".join(top_codes)

    all_dfs = []
    chunk_start = pd.Timestamp(start_date)
    chunk_end = pd.Timestamp(end_date)

    while chunk_start <= chunk_end:
        # 3-month chunks
        cs = chunk_start
        ce = min(chunk_start + timedelta(days=100), chunk_end)
        cs_str = cs.strftime('%Y-%m-%d')
        ce_str = ce.strftime('%Y-%m-%d')

        logger.info(f"  loading chunk {cs_str} ~ {ce_str}...")
        for attempt in range(3):
            try:
                conn = get_connection()
                try:
                    sql = (
                        f"SELECT stock_code, trade_date, close_price "
                        f"FROM trade_stock_daily "
                        f"WHERE trade_date >= '{cs_str}' AND trade_date <= '{ce_str}' "
                        f"AND stock_code IN ('{code_list}')"
                    )
                    df_chunk = pd.read_sql(sql, conn)
                finally:
                    conn.close()
                if not df_chunk.empty:
                    all_dfs.append(df_chunk)
                break
            except Exception as e:
                wait = 10 * (attempt + 1)
                logger.warning(f"  retry {attempt+1}: {e}, wait {wait}s")
                if attempt < 2:
                    import time as _time
                    _time.sleep(wait)
                else:
                    logger.error(f"  failed chunk {cs_str} ~ {ce_str}: {e}")

        chunk_start = ce + timedelta(days=1)

    if not all_dfs:
        return pd.DataFrame()

    df = pd.concat(all_dfs, ignore_index=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')

    logger.info(f"  loaded {len(df):,} rows in {time()-t0:.1f}s")

    # 3. Build equal-weight index (simpler and more robust than MC-weighted)
    daily_avg = df.groupby('trade_date')['close_price'].mean()
    result = daily_avg.to_frame('close')
    result.index.name = 'trade_date'

    # 4. Compute cross-sectional daily return std (regime proxy)
    pivot = df.pivot_table(index='trade_date', columns='stock_code',
                          values='close_price', aggfunc='first')
    daily_returns = pivot.pct_change()
    cross_section_std = daily_returns.std(axis=1)  # cross-sectional std each day

    result['cross_section_std'] = cross_section_std

    logger.info(f"Market index: {len(result)} days")
    return result


# ---------------------------------------------------------------------------
# Regime Analysis
# ---------------------------------------------------------------------------

def calc_regime_indicators(market_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate market regime indicators from daily market data.

    Indicators:
    - vol_20: 20-day rolling mean of cross-sectional return std
    - mom_20: market index 20-day momentum
    - drawdown_60: max drawdown over 60 days
    """
    df = market_daily.copy()

    # 20-day realized volatility of market index
    df['index_ret'] = df['close'].pct_change()
    df['index_vol_20'] = df['index_ret'].rolling(20).std() * np.sqrt(252)

    # 20-day momentum of market index
    df['mom_20'] = df['close'] / df['close'].shift(20) - 1

    # 60-day max drawdown
    rolling_max = df['close'].rolling(60, min_periods=20).max()
    df['drawdown_60'] = df['close'] / rolling_max - 1

    # 20-day rolling mean of cross-sectional std (market dispersion)
    df['cross_vol_20'] = df['cross_section_std'].rolling(20).mean()

    return df


def get_regime_at_dates(regime_df: pd.DataFrame, dates: list) -> pd.DataFrame:
    """Extract regime indicators at specific dates (use last available)."""
    results = []
    for dt in dates:
        mask = regime_df.index <= dt
        if not mask.any():
            results.append({
                'date': dt, 'vol_20': np.nan, 'mom_20': np.nan,
                'drawdown_60': np.nan, 'cross_vol_20': np.nan,
            })
            continue
        last_dt = regime_df.index[mask][-1]
        row = regime_df.loc[last_dt]
        results.append({
            'date': dt,
            'vol_20': row.get('index_vol_20', np.nan),
            'mom_20': row.get('mom_20', np.nan),
            'drawdown_60': row.get('drawdown_60', np.nan),
            'cross_vol_20': row.get('cross_vol_20', np.nan),
        })
    return pd.DataFrame(results).set_index('date')


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

def backtest_monthly(factor_dates, panel, prices, market_daily,
                     selector, blacklist, industry_map, top_n):
    """
    Monthly rebalancing backtest.

    For each month start:
    1. Select top N stocks with industry cap
    2. Buy at close on rebalance date
    3. Sell at close on next rebalance date
    4. Equal-weight portfolio return
    """
    bm = market_daily['close'] if not market_daily.empty else pd.Series(dtype=float)

    results = []
    for i, dt in enumerate(factor_dates):
        sell_dt = factor_dates[i + 1] if i + 1 < len(factor_dates) else None

        # Get cross-section for this date
        try:
            df_day = panel.loc[dt]
        except KeyError:
            logger.warning(f"No factor data for {dt.strftime('%Y-%m-%d')}, skip")
            continue
        if isinstance(df_day, pd.Series):
            continue

        # Select stocks
        top_stocks = selector.select_top_n(
            df_day, top_n=top_n, blacklist=blacklist, industry_map=industry_map
        )
        if not top_stocks:
            logger.warning(f"No stocks selected for {dt.strftime('%Y-%m-%d')}, skip")
            continue

        # Calculate individual stock returns
        stock_returns = []
        for code in top_stocks:
            try:
                buy_price = prices.loc[(dt, code), 'close_price']
            except KeyError:
                continue
            if buy_price is None or buy_price <= 0 or np.isnan(buy_price):
                continue

            if sell_dt is not None:
                try:
                    sell_price = prices.loc[(sell_dt, code), 'close_price']
                except KeyError:
                    continue
                if sell_price is None or sell_price <= 0 or np.isnan(sell_price):
                    continue
                stock_returns.append(float(sell_price) / float(buy_price) - 1)
            # Last period: no sell date yet

        port_ret = np.mean(stock_returns) if stock_returns else 0.0

        # Benchmark return
        bm_ret = 0.0
        if sell_dt is not None:
            try:
                bm_buy = bm.loc[dt]
                bm_sell = bm.loc[sell_dt]
                if bm_buy > 0 and not np.isnan(bm_buy):
                    bm_ret = float(bm_sell) / float(bm_buy) - 1
            except KeyError:
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
        })

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    # Cumulative returns
    df['cum_strat'] = (1 + df['portfolio_return']).cumprod() - 1
    df['cum_bm'] = (1 + df['benchmark_return']).cumprod() - 1
    df['cum_excess'] = (1 + df['excess_return']).cumprod() - 1

    return df


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def fmt_pct(val, plus_sign=True):
    """Format percentage with sign."""
    if np.isnan(val):
        return '-'
    s = f"{val:.2%}"
    if plus_sign and val > 0:
        s = '+' + s
    return s


def report_plan_a(results: pd.DataFrame, regime_at: pd.DataFrame):
    """
    Print Plan A report:
    1. Monthly returns table with regime indicators
    2. Summary statistics
    3. Regime effectiveness analysis
    """
    n = len(results)
    has_regime = not regime_at.empty

    print("\n" + "=" * 100)
    print("PLAN A: Monthly Rebalancing Backtest (Unconditional)")
    print("=" * 100)

    # --- Monthly returns table ---
    print(f"\n| Month | N | Portfolio | Benchmark | Excess | CumStrat | CumBM | "
          f"Vol20 | Mom20 | DD60 | CrossVol |")
    print(f"|-------|---|-----------|-----------|--------|----------|-------|"
          f"-------|-------|------|----------|")

    for _, row in results.iterrows():
        dt = row['rebalance_date']
        mark = ' *' if row['excess_return'] > 0 else ''

        if has_regime and dt in regime_at.index:
            r = regime_at.loc[dt]
            vol = fmt_pct(r['vol_20'], False)
            mom = fmt_pct(r['mom_20'])
            dd = fmt_pct(r['drawdown_60'])
            cv = fmt_pct(r['cross_vol_20'], False)
        else:
            vol = mom = dd = cv = '-'

        print(f"| {row['month']} | {row['n_stocks']} "
              f"| {fmt_pct(row['portfolio_return'])} "
              f"| {fmt_pct(row['benchmark_return'])} "
              f"| {fmt_pct(row['excess_return'])} "
              f"| {fmt_pct(row['cum_strat'])} "
              f"| {fmt_pct(row['cum_bm'])} "
              f"| {vol} | {mom} | {dd} | {cv} |{mark}")

    # --- Summary statistics ---
    total_strat = (1 + results['portfolio_return']).prod() - 1
    total_bm = (1 + results['benchmark_return']).prod() - 1
    total_excess = total_strat - total_bm

    excess = results['excess_return']
    avg_excess = excess.mean()
    std_excess = excess.std()
    win_rate = (excess > 0).mean()
    sharpe = avg_excess / std_excess * np.sqrt(12) if std_excess > 0 else 0

    # Max drawdown of cumulative excess
    cum_exc = (1 + excess).cumprod()
    peak = cum_exc.cummax()
    dd_series = (cum_exc - peak) / peak
    max_dd = dd_series.min()

    # Best / worst months
    best_idx = excess.idxmax()
    worst_idx = excess.idxmin()

    print(f"\n### Summary Statistics ({n} months)\n")
    print(f"| Metric | Value |")
    print(f"|--------|-------|")
    print(f"| Total Return (Strategy) | {total_strat:.2%} |")
    print(f"| Total Return (Benchmark) | {total_bm:.2%} |")
    print(f"| Total Excess Return | {total_excess:+.2%} |")
    print(f"| Avg Monthly Excess | {avg_excess:+.2%} |")
    print(f"| Monthly Excess Std | {std_excess:.2%} |")
    print(f"| Sharpe Ratio (ann.) | {sharpe:.2f} |")
    print(f"| Win Rate (excess > 0) | {win_rate:.0%} |")
    print(f"| Max Drawdown (excess) | {max_dd:.2%} |")
    print(f"| Best Month | {results.loc[best_idx, 'month']}: {fmt_pct(excess[best_idx])} |")
    print(f"| Worst Month | {results.loc[worst_idx, 'month']}: {fmt_pct(excess[worst_idx])} |")

    # --- Regime effectiveness ---
    if has_regime and len(regime_at) >= 6:
        print(f"\n### Regime Effectiveness Analysis\n")

        merged = results.copy().set_index('rebalance_date')
        common = merged.index.intersection(regime_at.dropna(subset=['vol_20', 'mom_20']).index)
        if len(common) < 4:
            logger.warning("Not enough common dates for regime analysis")
            return

        m = merged.loc[common].copy()
        m['vol_20'] = regime_at.loc[common, 'vol_20']
        m['mom_20'] = regime_at.loc[common, 'mom_20']
        m['cross_vol_20'] = regime_at.loc[common, 'cross_vol_20']

        def regime_stats(sub, label):
            if len(sub) == 0:
                return
            avg = sub['excess_return'].mean()
            wr = (sub['excess_return'] > 0).mean()
            total = (1 + sub['excess_return']).prod() - 1
            print(f"| {label} | {len(sub)} | {avg:+.2%} | {wr:.0%} | {total:+.2%} |")

        # 1. By market volatility
        vol_median = m['vol_20'].median()
        print(f"#### By Market Volatility (index vol_20 median = {vol_median:.1%})\n")
        print(f"| Regime | Months | Avg Excess | Win Rate | Cum Excess |")
        print(f"|--------|--------|------------|----------|------------|")
        regime_stats(m[m['vol_20'] >= vol_median], f"High Vol (>={vol_median:.1%})")
        regime_stats(m[m['vol_20'] < vol_median], f"Low Vol (<{vol_median:.1%})")

        # 2. By market dispersion (cross-sectional)
        if m['cross_vol_20'].notna().sum() > 4:
            cv_median = m['cross_vol_20'].median()
            print(f"\n#### By Market Dispersion (cross-section std median = {cv_median:.4f})\n")
            print(f"| Regime | Months | Avg Excess | Win Rate | Cum Excess |")
            print(f"|--------|--------|------------|----------|------------|")
            regime_stats(m[m['cross_vol_20'] >= cv_median],
                         f"High Dispersion (>={cv_median:.4f})")
            regime_stats(m[m['cross_vol_20'] < cv_median],
                         f"Low Dispersion (<{cv_median:.4f})")

        # 3. By market trend
        print(f"\n#### By Market Trend (prior 20d momentum)\n")
        print(f"| Regime | Months | Avg Excess | Win Rate | Cum Excess |")
        print(f"|--------|--------|------------|----------|------------|")
        regime_stats(m[m['mom_20'] < 0], "Declining (mom<0)")
        regime_stats(m[m['mom_20'] >= 0], "Rising (mom>=0)")
        regime_stats(m[m['mom_20'] < -0.03], "Strong Decline (mom<-3%)")
        regime_stats(m[m['mom_20'] >= 0.03], "Strong Rise (mom>3%)")

        # 4. Combined: high dispersion + declining
        print(f"\n#### Combined: High Dispersion + Declining\n")
        print(f"| Regime | Months | Avg Excess | Win Rate | Cum Excess |")
        print(f"|--------|--------|------------|----------|------------|")
        high_cv = m['cross_vol_20'] >= cv_median
        declining = m['mom_20'] < 0
        regime_stats(m[high_cv & declining], "High Disp + Declining")
        regime_stats(m[high_cv & ~declining], "High Disp + Rising")
        regime_stats(m[~high_cv & declining], "Low Disp + Declining")
        regime_stats(m[~high_cv & ~declining], "Low Disp + Rising")

        # 5. Per-month detail for winning/losing regimes
        print(f"\n### Month-by-Month Detail (sorted by excess return)\n")
        print(f"| Month | Excess | Vol20 | Mom20 | CrossVol | Active? |")
        print(f"|-------|--------|-------|-------|----------|---------|")
        sorted_m = m.sort_values('excess_return', ascending=False)
        for idx, row in sorted_m.iterrows():
            active = "YES" if row['excess_return'] > 0 else "no"
            print(f"| {row['month']} | {fmt_pct(row['excess_return'])} "
                  f"| {fmt_pct(row['vol_20'], False)} "
                  f"| {fmt_pct(row['mom_20'])} "
                  f"| {fmt_pct(row['cross_vol_20'], False)} "
                  f"| {active} |")

        return m

    return None


def report_plan_b(results_a: pd.DataFrame, regime_at: pd.DataFrame):
    """
    Plan B: Conditional backtest.
    Only activate strategy when regime conditions are met.
    Otherwise hold benchmark.
    """
    if regime_at.empty or len(regime_at.dropna(subset=['cross_vol_20', 'mom_20'])) < 6:
        print("\n[WARN] Cannot run Plan B: insufficient regime data")
        return

    print("\n" + "=" * 100)
    print("PLAN B: Conditional Backtest (Regime-Filtered)")
    print("=" * 100)

    merged = results_a.copy().set_index('rebalance_date')
    common = merged.index.intersection(regime_at.dropna(subset=['cross_vol_20', 'mom_20']).index)
    if len(common) < 4:
        print("[WARN] Not enough overlap for Plan B")
        return

    m = merged.loc[common].copy()
    m['cross_vol_20'] = regime_at.loc[common, 'cross_vol_20']
    m['mom_20'] = regime_at.loc[common, 'mom_20']
    m['vol_20'] = regime_at.loc[common, 'vol_20']

    # Define conditions
    cv_threshold = m['cross_vol_20'].quantile(0.60)
    declining = m['mom_20'] < 0

    # Condition sets to try
    conditions = {
        'A: cross_vol>=60pct + declining': (m['cross_vol_20'] >= cv_threshold) & declining,
        'B: cross_vol>=50pct + declining': (m['cross_vol_20'] >= m['cross_vol_20'].quantile(0.50)) & declining,
        'C: cross_vol>=60pct only': m['cross_vol_20'] >= cv_threshold,
        'D: declining only': declining,
        'E: index_vol>=median + declining': (m['vol_20'] >= m['vol_20'].median()) & declining,
    }

    # Compare all conditions
    print(f"\n### Condition Comparison\n")
    print(f"| Condition | Active | Avg Exc(A) | Avg Exc(B) | Sharpe(B) | Total Exc(B) |")
    print(f"|-----------|--------|------------|------------|-----------|--------------|")

    plan_b_best = None
    plan_b_best_name = None
    best_sharpe = -999

    for name, mask in conditions.items():
        active = mask.sum()
        if active == 0:
            continue

        # Plan B returns: strategy when active, benchmark when not
        plan_b_ret = np.where(mask, m['portfolio_return'], m['benchmark_return'])
        exc_b = plan_b_ret - m['benchmark_return']
        avg_exc_b = exc_b.mean()
        std_exc_b = exc_b.std()
        sharpe_b = avg_exc_b / std_exc_b * np.sqrt(12) if std_exc_b > 0 else 0
        total_exc_b = (1 + exc_b).prod() - 1

        # Active-only stats
        active_exc = m.loc[mask, 'excess_return']
        avg_exc_a = active_exc.mean() if len(active_exc) > 0 else 0

        print(f"| {name} | {active}/{len(m)} | {avg_exc_a:+.2%} | "
              f"{avg_exc_b:+.2%} | {sharpe_b:.2f} | {total_exc_b:+.2%} |")

        if sharpe_b > best_sharpe:
            best_sharpe = sharpe_b
            plan_b_best = mask
            plan_b_best_name = name

    if plan_b_best is None:
        return

    # Detailed report for best condition
    print(f"\n### Best Condition: {plan_b_best_name}\n")
    print(f"Threshold: cross_vol >= {cv_threshold:.4f} (60th pct) AND mom_20 < 0\n")

    plan_b_ret = np.where(plan_b_best, m['portfolio_return'], m['benchmark_return'])
    m['plan_b_return'] = plan_b_ret
    m['plan_b_excess'] = plan_b_ret - m['benchmark_return']
    m['active'] = plan_b_best

    print(f"| Month | Active | Strat | Plan B | BM | Exc(A) | Exc(B) | CumExc(B) |")
    print(f"|-------|--------|-------|--------|-----|--------|--------|-----------|")

    cum_b = 1.0
    for _, row in m.iterrows():
        cum_b *= (1 + row['plan_b_excess'])
        act = "YES" if row['active'] else " no"
        print(f"| {row['month']} | {act} "
              f"| {fmt_pct(row['portfolio_return'])} "
              f"| {fmt_pct(row['plan_b_return'])} "
              f"| {fmt_pct(row['benchmark_return'])} "
              f"| {fmt_pct(row['excess_return'])} "
              f"| {fmt_pct(row['plan_b_excess'])} "
              f"| {fmt_pct(cum_b - 1)} |")

    # Final comparison
    total_a = (1 + m['excess_return']).prod() - 1
    total_b = (1 + m['plan_b_excess']).prod() - 1
    sharpe_a = m['excess_return'].mean() / m['excess_return'].std() * np.sqrt(12) \
        if m['excess_return'].std() > 0 else 0
    sharpe_b_val = m['plan_b_excess'].mean() / m['plan_b_excess'].std() * np.sqrt(12) \
        if m['plan_b_excess'].std() > 0 else 0

    n_active = plan_b_best.sum()

    print(f"\n### Final Comparison\n")
    print(f"| Metric | Plan A | Plan B | Improvement |")
    print(f"|--------|--------|--------|-------------|")
    print(f"| Active Months | {len(m)} | {n_active} | -{len(m)-n_active} months |")
    print(f"| Total Excess | {total_a:+.2%} | {total_b:+.2%} | {total_b - total_a:+.2%} |")
    print(f"| Sharpe (excess) | {sharpe_a:.2f} | {sharpe_b_val:.2f} | {sharpe_b_val - sharpe_a:+.2f} |")
    print(f"| Avg Monthly Exc | {m['excess_return'].mean():+.2%} | {m['plan_b_excess'].mean():+.2%} | "
          f"{m['plan_b_excess'].mean() - m['excess_return'].mean():+.2%} |")

    return m


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Monthly Factor Backtest with Regime Analysis'
    )
    parser.add_argument('--start', default='2025-04-01',
                        help='Start date (YYYY-MM-DD), default 2025-04-01 (PB/PE data starts 2025-03-24)')
    parser.add_argument('--end', default=None,
                        help='End date (YYYY-MM-DD), default: latest factor date')
    parser.add_argument('--top-n', type=int, default=DEFAULT_TOP_N,
                        help=f'Number of stocks to select (default: {DEFAULT_TOP_N})')
    parser.add_argument('--plan', choices=['a', 'b', 'both'], default='both',
                        help='Which plan(s) to run (default: both)')
    args = parser.parse_args()

    # Determine end date
    if args.end is None:
        # Use latest factor date
        conn = get_connection()
        try:
            df = pd.read_sql(
                "SELECT MAX(calc_date) FROM trade_stock_valuation_factor", conn
            )
            args.end = str(df.iloc[0, 0])
        finally:
            conn.close()

    logger.info("=" * 60)
    logger.info("Monthly Factor Backtest")
    logger.info(f"Period: {args.start} ~ {args.end}")
    logger.info(f"Top N: {args.top_n}")
    logger.info("=" * 60)

    t0_total = time()

    # 1. Get monthly factor dates
    factor_dates = get_monthly_factor_dates(args.start, args.end)
    if not factor_dates:
        logger.error("No factor dates found, exiting")
        return

    # 2. Load factor data for monthly dates only
    panel = load_factor_for_dates(factor_dates)
    if panel.empty:
        logger.error("No factor data loaded, exiting")
        return

    # 3. Load prices for buy/sell dates
    # Include one extra date after last rebalance for sell price
    price_dates = list(factor_dates) + [factor_dates[-1] + timedelta(days=35)]
    prices = load_prices_for_dates(price_dates)

    # 4. Load market index (for benchmark + regime)
    # Extend start by 90 days for regime warm-up
    regime_start = (pd.Timestamp(args.start) - timedelta(days=120)).strftime('%Y-%m-%d')
    regime_end = (pd.Timestamp(factor_dates[-1]) + timedelta(days=35)).strftime('%Y-%m-%d')
    market_daily = load_market_index(regime_start, regime_end)
    has_market = not market_daily.empty

    # 5. Calculate regime indicators
    if has_market:
        regime_df = calc_regime_indicators(market_daily)
        regime_at = get_regime_at_dates(regime_df, factor_dates)
        logger.info(f"Regime indicators: {regime_at.dropna().shape[0]}/{len(regime_at)} dates")
    else:
        regime_at = pd.DataFrame()

    # 6. Load filters
    logger.info("Loading stock filter and industry map...")
    blacklist = load_stock_filter()
    industry_map = load_industry_map()

    # 7. Create selector
    selector = FactorSelector()

    # 8. Run backtest
    logger.info(f"Running monthly backtest (top_n={args.top_n})...")
    t0_bt = time()
    results = backtest_monthly(
        factor_dates, panel, prices, market_daily,
        selector, blacklist, industry_map, args.top_n
    )
    logger.info(f"Backtest done in {time()-t0_bt:.1f}s: {len(results)} months")

    if results.empty:
        logger.error("No backtest results")
        return

    # 9. Reports
    ensure_output_dir()

    regime_merged = None

    if args.plan in ('a', 'both'):
        regime_merged = report_plan_a(results, regime_at)

        # Save
        out_path = os.path.join(OUTPUT_DIR, 'monthly_backtest_plan_a.csv')
        results.to_csv(out_path, index=False)
        logger.info(f"Plan A saved to {out_path}")

    if args.plan in ('b', 'both'):
        if regime_merged is None and not regime_at.empty:
            # Merge manually
            merged = results.copy().set_index('rebalance_date')
            common = merged.index.intersection(regime_at.dropna().index)
            regime_merged = merged.loc[common].copy()
            regime_merged['cross_vol_20'] = regime_at.loc[common, 'cross_vol_20']
            regime_merged['mom_20'] = regime_at.loc[common, 'mom_20']
            regime_merged['vol_20'] = regime_at.loc[common, 'vol_20']

        plan_b_result = report_plan_b(results, regime_at)
        if plan_b_result is not None:
            out_path = os.path.join(OUTPUT_DIR, 'monthly_backtest_plan_b.csv')
            plan_b_result.to_csv(out_path)
            logger.info(f"Plan B saved to {out_path}")

    logger.info(f"\nTotal time: {time()-t0_total:.1f}s")


if __name__ == '__main__':
    main()
