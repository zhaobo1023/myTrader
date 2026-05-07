# -*- coding: utf-8 -*-
"""
Hard-tech factor IC validation CLI

Usage:
    python -m strategist.hard_tech.run_selector --mode ic --start 2024-01-01
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
    IC_FORWARD_PERIOD, IC_MIN_SAMPLES, IC_MIN_DATES,
)
from strategist.hard_tech.data_loader import load_hardtech_panel, load_forward_returns

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
    traditional = ['revenue_growth', 'gross_margin', 'roe_ttm', 'mom_20', 'market_cap']

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


def main():
    parser = argparse.ArgumentParser(description='Hard-Tech Factor Selector')
    parser.add_argument('--mode', choices=['ic'], default='ic',
                        help='Run mode (currently only ic)')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')

    args = parser.parse_args()

    if args.mode == 'ic':
        mode_ic(args)


if __name__ == '__main__':
    main()
