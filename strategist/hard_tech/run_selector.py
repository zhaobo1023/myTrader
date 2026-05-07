# -*- coding: utf-8 -*-
"""
Hard-tech factor IC validation / backtest / select CLI

Usage:
    python -m strategist.hard_tech.run_selector --mode ic --start 2024-01-01
    python -m strategist.hard_tech.run_selector --mode backtest --start 2024-06-01 --top-n 20
    python -m strategist.hard_tech.run_selector --mode select --date 2025-05-08 --top-n 20
"""
import argparse
import logging
import os
import sys
from datetime import date
from time import time

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.hard_tech.config import (
    HARDTECH_FACTORS, FACTOR_LABELS, FACTOR_DIRECTIONS, FACTOR_GROUPS,
    TOP_N, INDUSTRY_MAX_WEIGHT,
    IC_FORWARD_PERIOD, IC_MIN_SAMPLES, IC_MIN_DATES,
)
from strategist.hard_tech.data_loader import (
    load_hardtech_panel, load_forward_returns,
    load_single_day_factors, load_hardtech_universe,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(ROOT, 'output', 'hard_tech')


def calculate_ic_series(factor_panel, forward_returns, factor_name, period=IC_FORWARD_PERIOD):
    """Calculate IC time series for a single factor."""
    ret_col = f'forward_{period}d'
    if ret_col not in forward_returns.columns or factor_name not in factor_panel.columns:
        return pd.Series(dtype=float)

    dates = sorted(set(factor_panel.index.get_level_values(0))
                   & set(forward_returns.index.get_level_values(0)))

    ic_list = []
    for dt in dates:
        try:
            fv = factor_panel.loc[dt, factor_name]
            rv = forward_returns.loc[dt, ret_col]
            if isinstance(fv, (int, float)):
                continue
            common = fv.index.intersection(rv.index)
            if len(common) < IC_MIN_SAMPLES:
                continue
            ic, _ = spearmanr(fv[common], rv[common])
            if not np.isnan(ic):
                ic_list.append({'date': dt, 'ic': ic})
        except Exception:
            continue

    if not ic_list:
        return pd.Series(dtype=float)

    return pd.DataFrame(ic_list).set_index('date')['ic']


def evaluate_single_factor(factor_panel, forward_returns, factor_name, period=IC_FORWARD_PERIOD):
    """Evaluate a single factor's IC performance."""
    ic_series = calculate_ic_series(factor_panel, forward_returns, factor_name, period)

    if ic_series is None or len(ic_series) < IC_MIN_DATES:
        return {
            'factor': factor_name,
            'label': FACTOR_LABELS.get(factor_name, factor_name),
            'ic_mean': np.nan,
            'ic_std': np.nan,
            'icir': np.nan,
            'ic_count': len(ic_series) if ic_series is not None else 0,
            'positive_ratio': np.nan,
            'status': 'insufficient_data',
        }

    ic_clean = ic_series.dropna()
    ic_mean = ic_clean.mean()
    ic_std = ic_clean.std()
    icir = ic_mean / ic_std if ic_std > 1e-10 else 0.0
    pos_ratio = (ic_clean > 0).mean()

    direction = FACTOR_DIRECTIONS.get(factor_name, 1)
    if direction == -1:
        eval_ic_mean = -ic_mean
        eval_icir = -icir
    else:
        eval_ic_mean = ic_mean
        eval_icir = icir

    status = 'valid' if (abs(eval_ic_mean) >= 0.02 and abs(eval_icir) >= 0.3) else 'weak'

    return {
        'factor': factor_name,
        'label': FACTOR_LABELS.get(factor_name, factor_name),
        'ic_mean': round(ic_mean, 4),
        'ic_std': round(ic_std, 4),
        'icir': round(icir, 4),
        'ic_count': len(ic_clean),
        'positive_ratio': round(pos_ratio, 4),
        'eval_ic_mean': round(eval_ic_mean, 4),
        'eval_icir': round(eval_icir, 4),
        'status': status,
    }


def mode_ic(args):
    """IC analysis mode: evaluate all hard-tech factors."""
    logger.info("=" * 60)
    logger.info("MODE: Hard-Tech IC Analysis")
    logger.info("=" * 60)

    start = args.start or '2024-01-01'
    end = args.end or date.today().strftime('%Y-%m-%d')

    # Load data
    t0 = time()
    panel = load_hardtech_panel(start, end)
    fwd = load_forward_returns(start, end, periods=(IC_FORWARD_PERIOD,))
    logger.info(f"Data loaded in {time()-t0:.1f}s")

    if panel.empty:
        logger.error("No factor data loaded")
        return

    # Log panel stats
    logger.info(f"Panel: {len(panel):,} rows, {panel.index.get_level_values(0).nunique()} dates, "
                f"{panel.index.get_level_values(1).nunique()} stocks")

    # Evaluate each factor
    results = []
    for f in HARDTECH_FACTORS:
        if f in panel.columns:
            logger.info(f"Evaluating factor: {f} ({FACTOR_LABELS.get(f, f)})")
            result = evaluate_single_factor(panel, fwd, f, IC_FORWARD_PERIOD)
            results.append(result)
        else:
            logger.warning(f"Factor {f} not found in panel")

    # Print report
    print("\n# Hard-Tech Factor IC Report\n")
    print(f"Period: {start} ~ {end}")
    print(f"Forward period: {IC_FORWARD_PERIOD} trading days\n")

    print("| Factor | Label | IC Mean | ICIR | Count | Positive % | Status |")
    print("|--------|-------|---------|------|-------|------------|--------|")

    for r in results:
        status_mark = "[OK]" if r['status'] == 'valid' else "[WARN]" if r['status'] == 'weak' else "[N/A]"
        ic_mean = f"{r['ic_mean']:.4f}" if not np.isnan(r['ic_mean']) else "N/A"
        icir = f"{r['icir']:.4f}" if not np.isnan(r['icir']) else "N/A"
        pos = f"{r['positive_ratio']:.2%}" if not np.isnan(r['positive_ratio']) else "N/A"
        print(f"| {r['factor']} | {r['label']} | {ic_mean} | {icir} | {r['ic_count']} | {pos} | {status_mark} |")

    # Summary
    valid = [r for r in results if r['status'] == 'valid']
    weak = [r for r in results if r['status'] == 'weak']
    insufficient = [r for r in results if r['status'] == 'insufficient_data']

    print(f"\n**Valid factors**: {len(valid)}")
    print(f"**Weak factors**: {len(weak)}")
    print(f"**Insufficient data**: {len(insufficient)}")

    if valid:
        print("\n## Valid Factors\n")
        for r in valid:
            print(f"- **{r['label']}** ({r['factor']}): IC={r['ic_mean']:.4f}, ICIR={r['icir']:.4f}")

    if weak:
        print("\n## Weak Factors\n")
        for r in weak:
            print(f"- **{r['label']}** ({r['factor']}): IC={r['ic_mean']:.4f}, ICIR={r['icir']:.4f}")

    # Compare hardtech vs traditional factors
    hardtech_only = ['rd_intensity', 'rd_growth', 'rd_efficiency', 'gross_margin_trend']

    print("\n## Hard-tech vs Traditional Comparison\n")
    print("| Category | Factor | IC Mean | ICIR | Status |")
    print("|----------|--------|---------|------|--------|")
    for r in results:
        cat = "Hard-tech" if r['factor'] in hardtech_only else "Traditional"
        ic_mean = f"{r['ic_mean']:.4f}" if not np.isnan(r['ic_mean']) else "N/A"
        icir = f"{r['icir']:.4f}" if not np.isnan(r['icir']) else "N/A"
        print(f"| {cat} | {r['factor']} | {ic_mean} | {icir} | {r['status']} |")

    # Save report
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save IC series CSV
    ic_data = []
    for f in HARDTECH_FACTORS:
        if f in panel.columns:
            ic_s = calculate_ic_series(panel, fwd, f, IC_FORWARD_PERIOD)
            if not ic_s.empty:
                ic_s.name = f
                ic_data.append(ic_s.to_frame())

    if ic_data:
        ic_df = pd.concat(ic_data, axis=1)
        ic_path = os.path.join(OUTPUT_DIR, 'ic_series.csv')
        ic_df.to_csv(ic_path)
        logger.info(f"IC series saved to {ic_path}")

    logger.info("IC analysis complete")


def mode_backtest(args):
    """Backtest mode: test portfolio returns with hard-tech factor scoring."""
    logger.info("=" * 60)
    logger.info("MODE: Hard-Tech Backtest")
    logger.info("=" * 60)

    start = args.start or '2024-06-01'
    end = args.end or date.today().strftime('%Y-%m-%d')
    top_n = args.top_n or TOP_N

    from strategist.multi_factor.scorer import FactorSelector

    # Load data
    t0 = time()
    panel = load_hardtech_panel(start, end)
    fwd = load_forward_returns(start, end, periods=(5, 20))
    logger.info(f"Data loaded in {time()-t0:.1f}s")

    if panel.empty:
        logger.error("No factor data loaded")
        return

    # Load universe for industry mapping
    universe = load_hardtech_universe()
    industry_map = dict(zip(universe['stock_code'], universe['sw_industry'])) if not universe.empty else None

    # Create selector with hardtech factor groups
    selector = FactorSelector(
        use_groups=True,
        factor_groups=FACTOR_GROUPS,
        factor_directions=FACTOR_DIRECTIONS,
    )

    available_factors = [f for f in selector.factors if f in panel.columns]
    logger.info(f"Available factors: {available_factors}")

    # Test multiple rebalance frequencies
    freqs = {'weekly (5d)': 5, 'monthly (20d)': 20}
    all_results = {}

    for freq_label, freq in freqs.items():
        logger.info(f"\n--- Backtest: {freq_label} rebalance, top_n={top_n} ---")
        dates = panel.index.get_level_values(0).unique().sort_values()
        rebalance_dates = dates.tolist()[::freq]

        portfolio_returns = []
        selection_records = []

        for i, dt in enumerate(rebalance_dates):
            df_day = panel.loc[dt]
            if isinstance(df_day, pd.Series):
                continue

            # Filter to hardtech universe
            if industry_map:
                universe_codes = set(industry_map.keys())
                df_day = df_day[df_day.index.isin(universe_codes)]

            if len(df_day) < top_n:
                logger.info(f"  {dt.strftime('%Y-%m-%d')}: only {len(df_day)} stocks, skipping")
                continue

            # Score and select
            scores = selector.score_cross_section(df_day[available_factors])
            ranked = scores.sort_values(ascending=False)

            # Apply industry cap
            if industry_map:
                cap = max(1, int(top_n * INDUSTRY_MAX_WEIGHT))
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
                    if count < cap:
                        selected.append(code)
                        industry_count[ind] = count + 1
                        if len(selected) >= top_n:
                            break
                top_stocks = selected
            else:
                top_stocks = ranked.head(top_n).index.tolist()

            if not top_stocks:
                continue

            # Record selections
            for rank, code in enumerate(top_stocks, 1):
                selection_records.append({
                    'trade_date': dt,
                    'stock_code': code,
                    'rank': rank,
                    'composite_score': round(scores.get(code, np.nan), 4),
                })

            # Calculate holding period return
            period = 20 if freq == 20 else 5

            stock_rets = []
            for code in top_stocks:
                if (dt, code) not in panel.index and (dt, code) not in fwd.index:
                    continue
                # Use forward returns if available
                fwd_col = f'forward_{period}d'
                if fwd_col in fwd.columns and (dt, code) in fwd.index:
                    ret = fwd.loc[(dt, code), fwd_col]
                    if not np.isnan(ret):
                        stock_rets.append(ret)

            if stock_rets:
                port_ret = np.mean(stock_rets)
                portfolio_returns.append({
                    'trade_date': dt,
                    'portfolio_return': port_ret,
                    'n_stocks': len(stock_rets),
                })

            if (i + 1) % 5 == 0:
                logger.info(f"  Rebalance {i+1}/{len(rebalance_dates)}: {dt.strftime('%Y-%m-%d')}")

        if not portfolio_returns:
            logger.warning(f"No portfolio returns for {freq_label}")
            continue

        ret_df = pd.DataFrame(portfolio_returns)
        ret_df['cumulative_return'] = (1 + ret_df['portfolio_return']).cumprod() - 1

        # Calculate metrics
        total_return = ret_df['cumulative_return'].iloc[-1]
        max_dd = (ret_df['cumulative_return'].cummax() - ret_df['cumulative_return']).max()
        mean_ret = ret_df['portfolio_return'].mean()
        std_ret = ret_df['portfolio_return'].std()
        sharpe = mean_ret / std_ret * np.sqrt(252 / freq) if std_ret > 0 else 0
        win_rate = (ret_df['portfolio_return'] > 0).mean()

        metrics = {
            'freq_label': freq_label,
            'freq': freq,
            'n_rebalances': len(ret_df),
            'total_return': round(total_return, 4),
            'max_drawdown': round(max_dd, 4),
            'mean_return': round(mean_ret, 4),
            'std_return': round(std_ret, 4),
            'sharpe': round(sharpe, 4),
            'win_rate': round(win_rate, 4),
        }
        all_results[freq_label] = metrics

    # Print comparison
    print("\n# Hard-Tech Backtest Report\n")
    print(f"Period: {start} ~ {end}")
    print(f"Top N: {top_n}")
    print(f"Industry max weight: {INDUSTRY_MAX_WEIGHT:.0%}\n")

    print("| Metric | Weekly (5d) | Monthly (20d) |")
    print("|--------|-------------|---------------|")
    metric_rows = [
        ('Total Return', 'total_return'),
        ('Max Drawdown', 'max_drawdown'),
        ('Mean Return', 'mean_return'),
        ('Std Return', 'std_return'),
        ('Sharpe Ratio', 'sharpe'),
        ('Win Rate', 'win_rate'),
        ('Rebalances', 'n_rebalances'),
    ]
    for label, key in metric_rows:
        vals = []
        for freq_label in freqs:
            m = all_results.get(freq_label, {})
            v = m.get(key, np.nan)
            if key in ('total_return', 'max_drawdown', 'mean_return', 'std_return', 'win_rate'):
                vals.append(f"{v:.2%}" if not np.isnan(v) else "N/A")
            elif key == 'sharpe':
                vals.append(f"{v:.2f}" if not np.isnan(v) else "N/A")
            else:
                vals.append(str(int(v)) if not np.isnan(v) else "N/A")
        print(f"| {label} | {vals[0]} | {vals[1]} |")

    # Save backtest results
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    sel_df = pd.DataFrame(selection_records)
    if not sel_df.empty:
        sel_path = os.path.join(OUTPUT_DIR, 'backtest_selections.csv')
        sel_df.to_csv(sel_path, index=False)
        logger.info(f"Selections saved to {sel_path}")

    logger.info("Backtest complete")


def mode_select(args):
    """Select mode: single-day stock selection output."""
    logger.info("=" * 60)
    logger.info("MODE: Hard-Tech Single-Day Selection")
    logger.info("=" * 60)

    from strategist.multi_factor.scorer import FactorSelector

    trade_date = args.date or date.today().strftime('%Y-%m-%d')
    top_n = args.top_n or TOP_N

    t0 = time()
    universe = load_hardtech_universe()
    stock_codes = universe['stock_code'].tolist()
    industry_map = dict(zip(universe['stock_code'], universe['sw_industry']))
    name_map = dict(zip(universe['stock_code'], universe['stock_name']))

    if not stock_codes:
        logger.error("Empty hardtech universe")
        return

    factors_df = load_single_day_factors(trade_date, stock_codes)
    logger.info(f"Data loaded in {time()-t0:.1f}s")

    if factors_df.empty:
        logger.error(f"No factor data for {trade_date}")
        return

    # Score
    selector = FactorSelector(
        use_groups=True,
        factor_groups=FACTOR_GROUPS,
        factor_directions=FACTOR_DIRECTIONS,
    )
    scores = selector.score_cross_section(factors_df)
    ranked = scores.sort_values(ascending=False)

    # Apply industry cap
    cap = max(1, int(top_n * INDUSTRY_MAX_WEIGHT))
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
        if count < cap:
            selected.append(code)
            industry_count[ind] = count + 1
            if len(selected) >= top_n:
                break

    # Print results
    print(f"\n# Hard-Tech Stock Selection: {trade_date}\n")
    print(f"Universe: {len(stock_codes)} stocks | Top N: {top_n} | Industry cap: {INDUSTRY_MAX_WEIGHT:.0%}\n")

    print("| # | Code | Name | Industry | Score | R&D Int | R&D Grw | R&D Eff | "
          "GM Trend | Rev G | NP G | RPS250 | MOM20 | PE-TTM |")
    print("|---|------|------|----------|-------|--------|---------|--------|"
          "----------|-------|------|-------|-------|--------|")

    display_factors = [
        'rd_intensity', 'rd_growth', 'rd_efficiency', 'gross_margin_trend',
        'revenue_growth', 'net_profit_growth', 'rps_250', 'mom_20', 'pe_ttm',
    ]

    for rank, code in enumerate(selected, 1):
        name = name_map.get(code, '--')
        ind = industry_map.get(code, '--')
        score = f"{scores.get(code, 0):.3f}"

        factor_vals = []
        for f in display_factors:
            if f in factors_df.columns and code in factors_df.index:
                v = factors_df.loc[code, f]
                if pd.notna(v):
                    factor_vals.append(f"{v:.3f}")
                else:
                    factor_vals.append("--")
            else:
                factor_vals.append("--")

        print(f"| {rank} | {code} | {name} | {ind} | {score} | "
              + " | ".join(factor_vals) + " |")

    # Industry distribution
    if industry_count:
        print("\n## Industry Distribution\n")
        for ind, count in sorted(industry_count.items(), key=lambda x: -x[1]):
            print(f"- {ind}: {count}/{top_n} ({count/top_n:.0%})")

    logger.info(f"Selection complete: {len(selected)} stocks for {trade_date}")


def main():
    parser = argparse.ArgumentParser(description='Hard-Tech Factor Selector')
    parser.add_argument('--mode', choices=['ic', 'backtest', 'select'], default='ic',
                        help='Run mode: ic / backtest / select')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--date', type=str, help='Trade date for select mode (YYYY-MM-DD)')
    parser.add_argument('--top-n', type=int, help=f'Number of stocks to select (default: {TOP_N})')

    args = parser.parse_args()

    if args.mode == 'ic':
        mode_ic(args)
    elif args.mode == 'backtest':
        mode_backtest(args)
    elif args.mode == 'select':
        mode_select(args)


if __name__ == '__main__':
    main()
