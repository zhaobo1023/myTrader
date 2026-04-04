# -*- coding: utf-8 -*-
"""
多因子选股 CLI 入口

Usage:
    # IC analysis
    python -m strategist.multi_factor.run_selector --mode ic --start 2024-01-01

    # Single day selection
    python -m strategist.multi_factor.run_selector --mode select --date 2026-03-24 --top-n 50

    # Backtest
    python -m strategist.multi_factor.run_selector --mode backtest --start 2024-06-01 --top-n 50
"""

import argparse
import logging
import os
import sys
from datetime import date
from time import time

import pandas as pd

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.multi_factor.config import (
    FACTORS, FACTOR_LABELS, FACTOR_DIRECTIONS, DEFAULT_TOP_N,
    DEFAULT_REBALANCE_FREQ, IC_FORWARD_PERIOD,
)
from strategist.multi_factor.data_loader import load_factor_panel, load_forward_returns, load_stock_filter, load_industry_map
from strategist.multi_factor.scorer import FactorSelector, calc_backtest_returns
from strategist.multi_factor.evaluator import (
    evaluate_all_factors, evaluate_single_factor,
    calculate_ic_series, format_ic_report,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(ROOT, 'output', 'multi_factor')


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def mode_ic(args):
    """IC analysis mode: evaluate all factors + composite score."""
    logger.info("=" * 60)
    logger.info("MODE: IC Analysis")
    logger.info("=" * 60)

    start = args.start or '2024-01-01'
    end = args.end or date.today().strftime('%Y-%m-%d')

    # 1. Load data
    t0 = time()
    panel = load_factor_panel(start, end)
    fwd = load_forward_returns(start, end, periods=(IC_FORWARD_PERIOD,))
    logger.info(f"Data loaded in {time()-t0:.1f}s")

    if panel.empty:
        logger.error("No factor data loaded")
        return

    # 2. Evaluate single factors
    logger.info("\n[1] Evaluating single factors...")
    results = evaluate_all_factors(panel, fwd, period=IC_FORWARD_PERIOD)
    report = format_ic_report(results)
    print(report)

    # 3. Evaluate composite score (equal-weight)
    logger.info("\n[2] Evaluating composite score (equal-weight)...")
    selector = FactorSelector()
    score_panel = selector.score_panel(panel)
    if not score_panel.empty:
        # merge on index, handle potential duplicates
        combined = panel.reset_index().merge(
            score_panel.reset_index(), on=['trade_date', 'stock_code'], how='inner'
        ).set_index(['trade_date', 'stock_code'])
        composite_result = evaluate_single_factor(
            combined, fwd, 'composite_score', IC_FORWARD_PERIOD
        )
        composite_result['label'] = 'Composite (Equal-Weight)'
        results.append(composite_result)

        report2 = format_ic_report([composite_result])
        print("\n## Composite Score IC (Equal-Weight)\n")
        print(report2)

    # 4. Evaluate composite score (group-weight)
    logger.info("\n[3] Evaluating composite score (group-weight)...")
    selector_grp = FactorSelector(use_groups=True)
    score_panel_grp = selector_grp.score_panel(panel)
    if not score_panel_grp.empty:
        combined_grp = panel.reset_index().merge(
            score_panel_grp.reset_index(), on=['trade_date', 'stock_code'], how='inner'
        ).set_index(['trade_date', 'stock_code'])
        grp_result = evaluate_single_factor(
            combined_grp, fwd, 'composite_score', IC_FORWARD_PERIOD
        )
        grp_result['label'] = 'Composite (Group-Weight)'
        results.append(grp_result)

        report3 = format_ic_report([grp_result])
        print("\n## Composite Score IC (Group-Weight)\n")
        print(report3)

    # 5. Factor correlation matrix
    logger.info("\n[4] Computing factor correlation matrix...")
    factor_cols_all = FACTORS + ['composite_score']
    factor_cols_available = [c for c in factor_cols_all if c in panel.columns]
    # Use group-weight score panel for correlation matrix
    score_panel_for_corr = score_panel_grp if not score_panel_grp.empty else score_panel
    if 'composite_score' in score_panel_for_corr.columns and 'composite_score' not in panel.columns:
        panel_with_score = panel.reset_index().merge(
            score_panel_for_corr.reset_index(), on=['trade_date', 'stock_code'], how='inner'
        ).set_index(['trade_date', 'stock_code'])
    else:
        panel_with_score = panel

    corr_cols = [c for c in factor_cols_available if c in panel_with_score.columns]
    if corr_cols:
        # 取最近一个数据完整的交易日截面计算相关性
        all_dates = panel_with_score.index.get_level_values(0).unique().sort_values(ascending=False)
        last_date = None
        for dt in all_dates:
            df_try = panel_with_score.loc[dt]
            if isinstance(df_try, pd.DataFrame) and df_try[corr_cols].notna().mean().min() > 0.8:
                last_date = dt
                break
        if last_date is None:
            last_date = all_dates[0]
        df_last = panel_with_score.loc[last_date]
        if isinstance(df_last, pd.DataFrame):
            corr = df_last[corr_cols].corr()
            print("\n## Factor Correlation Matrix (cross-section)")
            print(f"(Date: {last_date.strftime('%Y-%m-%d')})\n")
            # Format for readability
            corr_fmt = corr.style.format("{:.3f}")
            print(corr_fmt.to_string())
            # Highlight high correlations
            high_corr_pairs = []
            for i in range(len(corr.columns)):
                for j in range(i+1, len(corr.columns)):
                    c1, c2 = corr.columns[i], corr.columns[j]
                    val = corr.iloc[i, j]
                    if abs(val) > 0.7:
                        high_corr_pairs.append((c1, c2, val))
            if high_corr_pairs:
                print(f"\n**High correlation pairs (|r| > 0.7):**")
                for c1, c2, v in high_corr_pairs:
                    label1 = FACTOR_LABELS.get(c1, c1)
                    label2 = FACTOR_LABELS.get(c2, c2)
                    print(f"  - {label1}({c1}) <-> {label2}({c2}): r={v:.3f}")

    # 6. Save report
    ensure_output_dir()
    report_path = os.path.join(OUTPUT_DIR, 'ic_report.md')
    full_report = format_ic_report(results)
    with open(report_path, 'w') as f:
        f.write(full_report)
    logger.info(f"Report saved to {report_path}")

    # Save IC series CSV
    ic_data = []
    for f in FACTORS + ['composite_score', 'composite_score_grp']:
        f_actual = f  # default: column name in DataFrame
        if f in panel.columns:
            src = panel
        elif f == 'composite_score_grp' and not score_panel_grp.empty:
            src = score_panel_grp
            f_actual = 'composite_score'
        elif f == 'composite_score' and not score_panel.empty:
            src = score_panel
        else:
            continue
        ic_s = calculate_ic_series(src, fwd, f_actual, IC_FORWARD_PERIOD)
        if not ic_s.empty:
            ic_s.name = f
            ic_data.append(ic_s.to_frame())

    if ic_data:
        ic_df = pd.concat(ic_data, axis=1)
        ic_path = os.path.join(OUTPUT_DIR, 'ic_series.csv')
        ic_df.to_csv(ic_path)
        logger.info(f"IC series saved to {ic_path}")


def mode_select(args):
    """Single-day selection mode."""
    logger.info("=" * 60)
    logger.info("MODE: Single Day Selection")
    logger.info("=" * 60)

    target_date = args.date
    top_n = args.top_n or DEFAULT_TOP_N

    # 加载目标日前后几天的数据(因子表日期可能略有偏移)
    from datetime import timedelta
    start = (pd.Timestamp(target_date) - timedelta(days=5)).strftime('%Y-%m-%d')
    end = target_date

    t0 = time()
    panel = load_factor_panel(start, end)
    logger.info(f"Data loaded in {time()-t0:.1f}s")

    if panel.empty:
        logger.error("No factor data loaded")
        return

    # 找最接近目标日的截面
    available_dates = panel.index.get_level_values(0).unique().sort_values()
    target_ts = pd.Timestamp(target_date)
    closest_date = available_dates[available_dates <= target_ts][-1] if len(available_dates) > 0 else None

    if closest_date is None:
        logger.error(f"No data on or before {target_date}")
        return

    logger.info(f"Using date: {closest_date.strftime('%Y-%m-%d')} (requested: {target_date})")

    df_day = panel.loc[closest_date]
    if isinstance(df_day, pd.Series):
        logger.error("Only one stock in cross-section")
        return

    selector = FactorSelector()

    # 加载黑名单
    logger.info("\n[0] Loading stock filter...")
    blacklist = load_stock_filter()
    n_before = len(df_day)
    df_day_filtered = df_day[~df_day.index.isin(blacklist)]
    n_after = len(df_day_filtered)
    logger.info(f"  after filter: {n_after}/{n_before} stocks")

    # 加载行业映射
    logger.info("\n[0b] Loading industry map...")
    industry_map = load_industry_map()

    # 1) 等权合成选股
    logger.info(f"\n[1] Equal-weight composite selection (Top {top_n})...")
    top_stocks = selector.select_top_n(df_day, top_n=top_n, blacklist=blacklist,
                                        industry_map=industry_map)
    scores = selector.score_cross_section(df_day)

    # 加载股票名称
    from config.db import get_connection
    conn = get_connection()
    try:
        name_df = pd.read_sql(
            "SELECT stock_code, stock_name FROM trade_stock_basic", conn
        )
        name_map = dict(zip(name_df['stock_code'], name_df['stock_name']))
    finally:
        conn.close()

    print(f"\n## Top {top_n} Stocks (Equal-Weight Composite)")
    print(f"Date: {closest_date.strftime('%Y-%m-%d')}")
    print(f"Universe: {n_after} stocks (after filtering)")
    from strategist.multi_factor.config import INDUSTRY_CAP_ENABLED, INDUSTRY_MAX_WEIGHT
    if INDUSTRY_CAP_ENABLED and industry_map:
        print(f"Industry cap: max {int(top_n * INDUSTRY_MAX_WEIGHT)}/industry ({INDUSTRY_MAX_WEIGHT:.0%})")
    print()
    print(f"| Rank | Code | Name | Industry | Score | PB | PE | MktCap | Vol20 | Price | ROE |")
    print(f"|------|------|------|----------|-------|----|----|--------|-------|-------|-----|")

    for i, code in enumerate(top_stocks, 1):
        row = df_day.loc[code]
        name = name_map.get(code, '')
        industry = industry_map.get(code, '-')
        mktcap = row.get('market_cap', 0)
        print(
            f"| {i} | {code} | {name} | {industry} | {scores[code]:.3f} | "
            f"{row.get('pb', 0):.2f} | {row.get('pe_ttm', 0):.2f} | "
            f"{mktcap:.2f} | {row.get('volatility_20', 0):.4f} | "
            f"{row.get('close', 0):.2f} | {row.get('roe_ttm', 0):.2f} |"
        )

    # 行业分布统计
    if industry_map:
        industry_dist = {}
        for code in top_stocks:
            ind = industry_map.get(code, 'unknown')
            industry_dist[ind] = industry_dist.get(ind, 0) + 1
        print(f"\n### Industry Distribution\n")
        for ind, cnt in sorted(industry_dist.items(), key=lambda x: -x[1]):
            bar = '#' * cnt
            print(f"  {ind}: {cnt} {bar}")

    # 2) 单因子 Top 10
    print("\n\n## Single Factor Top 10\n")
    for f in FACTORS:
        if f not in df_day.columns:
            continue
        direction = FACTOR_DIRECTIONS.get(f, 1)
        valid = df_day[f].dropna()
        if direction == -1:
            top10 = valid.nsmallest(10)
        else:
            top10 = valid.nlargest(10)

        label = FACTOR_LABELS.get(f, f)
        print(f"### {label} ({f})")
        print(f"| Rank | Stock | Value |")
        print(f"|------|-------|-------|")
        for rank, (code, val) in enumerate(top10.items(), 1):
            print(f"| {rank} | {code} | {val:.4f} |")
        print()

    # 3) Save
    ensure_output_dir()
    result_df = pd.DataFrame({
        'rank': range(1, len(top_stocks) + 1),
        'stock_code': top_stocks,
        'composite_score': [scores[c] for c in top_stocks],
    })
    out_path = os.path.join(OUTPUT_DIR, f"select_{closest_date.strftime('%Y%m%d')}.csv")
    result_df.to_csv(out_path, index=False)
    logger.info(f"Selection saved to {out_path}")


def mode_backtest(args):
    """Backtest mode."""
    logger.info("=" * 60)
    logger.info("MODE: Backtest")
    logger.info("=" * 60)

    start = args.start or '2024-06-01'
    end = args.end or date.today().strftime('%Y-%m-%d')
    top_n = args.top_n or DEFAULT_TOP_N
    rebalance_freq = args.rebalance_freq or DEFAULT_REBALANCE_FREQ

    # 1. Load data
    t0 = time()
    panel = load_factor_panel(start, end)
    logger.info(f"Factor panel loaded in {time()-t0:.1f}s: {len(panel):,} rows")

    # 2. Run selection
    logger.info(f"\n[1] Running selection (top_n={top_n}, rebalance_freq={rebalance_freq})...")
    t0 = time()
    selector = FactorSelector()
    selections = selector.select_panel(panel, top_n=top_n, rebalance_freq=rebalance_freq)
    logger.info(f"Selection done in {time()-t0:.1f}s")

    if selections.empty:
        logger.error("No selections generated")
        return

    # 3. Load close prices for return calculation
    logger.info("\n[2] Loading close prices...")
    from config.db import execute_query
    from datetime import timedelta
    end_ext = (pd.Timestamp(end) + timedelta(days=45)).strftime('%Y-%m-%d')
    sql = f"""
        SELECT stock_code, trade_date, close_price
        FROM trade_stock_daily
        WHERE trade_date >= '{start}' AND trade_date <= '{end_ext}'
        ORDER BY stock_code, trade_date
    """
    rows = execute_query(sql)
    if not rows:
        logger.error("No price data for backtest")
        return

    df_prices = pd.DataFrame(rows)
    df_prices['trade_date'] = pd.to_datetime(df_prices['trade_date'])
    df_prices['close_price'] = pd.to_numeric(df_prices['close_price'], errors='coerce')
    df_prices = df_prices.set_index(['trade_date', 'stock_code']).sort_index()

    # 4. Calculate returns
    logger.info("\n[3] Calculating portfolio returns...")
    bt_results = calc_backtest_returns(selections, df_prices)

    if bt_results.empty:
        logger.error("No backtest results")
        return

    # 5. Report
    total_return = bt_results['cumulative_return'].iloc[-1]
    n_rebalances = len(bt_results)
    avg_stocks = bt_results['n_stocks'].mean()
    win_rate = (bt_results['portfolio_return'] > 0).mean()

    # 年化收益 (假设 ~242 交易日/年)
    n_years = n_rebalances * rebalance_freq / 242
    annual_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1

    report_lines = [
        "# Multi-Factor Backtest Report\n",
        f"**Period**: {start} ~ {end}",
        f"**Top N**: {top_n}",
        f"**Rebalance Freq**: every {rebalance_freq} trading days",
        f"**Rebalances**: {n_rebalances}",
        f"**Avg Holdings**: {avg_stocks:.0f}\n",
        "## Performance\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Return | {total_return:.2%} |",
        f"| Annualized Return | {annual_return:.2%} |",
        f"| Win Rate | {win_rate:.2%} |",
        f"| Avg Stocks per Rebalance | {avg_stocks:.0f} |",
    ]

    print('\n'.join(report_lines))

    # 6. Save
    ensure_output_dir()
    out_csv = os.path.join(OUTPUT_DIR, 'backtest_returns.csv')
    bt_results.to_csv(out_csv, index=False)
    logger.info(f"Backtest returns saved to {out_csv}")

    sel_csv = os.path.join(OUTPUT_DIR, 'backtest_selections.csv')
    selections.to_csv(sel_csv, index=False)
    logger.info(f"Selections saved to {sel_csv}")

    report_path = os.path.join(OUTPUT_DIR, 'backtest_report.md')
    with open(report_path, 'w') as f:
        f.write('\n'.join(report_lines))
    logger.info(f"Report saved to {report_path}")


def main():
    parser = argparse.ArgumentParser(description='Multi-Factor Stock Selector')
    parser.add_argument('--mode', choices=['ic', 'select', 'backtest'], default='ic',
                        help='Run mode: ic analysis, single-day selection, or backtest')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--date', type=str, help='Target date for select mode (YYYY-MM-DD)')
    parser.add_argument('--top-n', type=int, help='Number of stocks to select')
    parser.add_argument('--rebalance-freq', type=int, help='Rebalance frequency in trading days')

    args = parser.parse_args()

    if args.mode == 'ic':
        mode_ic(args)
    elif args.mode == 'select':
        if not args.date:
            parser.error("--date is required for select mode")
        mode_select(args)
    elif args.mode == 'backtest':
        mode_backtest(args)


if __name__ == '__main__':
    main()
