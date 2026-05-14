# -*- coding: utf-8 -*-
"""
G-Score strategy CLI entry point

Usage:
    # Run screener for latest trade date
    python -m strategist.g_score.run_screener

    # Run for a specific date
    python -m strategist.g_score.run_screener --date 2026-05-13

    # Run with custom parameters
    python -m strategist.g_score.run_screener --top-n 20 --min-score 6

    # Show score distribution analysis
    python -m strategist.g_score.run_screener --analyze
"""

import argparse
import logging
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_screener(args):
    """Run G-Score screener and display results."""
    from strategist.g_score.screener import screen_g_score_stocks

    result_df = screen_g_score_stocks(
        trade_date=args.date,
        top_n=args.top_n,
        min_g_score=args.min_score,
        pb_percentile=args.pb_percentile,
        env=args.env,
    )

    if result_df.empty:
        print("\n[G-SCORE] No stocks meet the criteria.")
        return

    # Display results
    display_cols = ['stock_code', 'stock_name', 'industry', 'g_score',
                    'pb', 'pe_ttm', 'total_mv',
                    's_roa', 's_cfoa', 's_accrual', 's_rd',
                    's_sga', 's_capex', 's_roa_var', 's_rev_var']
    available = [c for c in display_cols if c in result_df.columns]

    print(f"\n{'='*80}")
    print(f"G-Score Strategy Results ({args.date or 'latest'})")
    print(f"{'='*80}")
    print(f"Selected: {len(result_df)} stocks")
    print(f"PB threshold: {args.pb_percentile}th percentile")
    print(f"Min G-Score: {args.min_score}")
    print(f"{'='*80}\n")

    for _, row in result_df.iterrows():
        code = row.get('stock_code', '')
        name = row.get('stock_name', '')
        industry = row.get('industry', '')
        gs = int(row.get('g_score', 0))
        pb = row.get('pb', 0)
        pe = row.get('pe_ttm', 0)
        mv = row.get('total_mv', 0)

        scores = []
        for s_col in ['s_roa', 's_cfoa', 's_accrual', 's_rd',
                      's_sga', 's_capex', 's_roa_var', 's_rev_var']:
            if s_col in row.index:
                scores.append(str(int(row[s_col])) if pd.notna(row[s_col]) else '?')
            else:
                scores.append('?')

        print(f"  {code:10s} {name:10s} | G-Score: {gs}/8 "
              f"({''.join(scores)}) | PB:{pb:.1f} PE:{pe:.1f} "
              f"MV:{mv:.0f}亿 | {industry}")

    # Score distribution
    print("\n--- Score Distribution ---")
    dist = result_df['g_score'].value_counts().sort_index(ascending=False)
    for score, count in dist.items():
        bar = '#' * count
        print(f"  G-Score {int(score)}: {count:3d} {bar}")

    # Save to CSV if requested
    if args.output:
        output_path = os.path.join(ROOT, 'output', 'g_score')
        os.makedirs(output_path, exist_ok=True)
        filename = args.output
        filepath = os.path.join(output_path, filename)
        result_df[available].to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"\nResults saved to: {filepath}")


def run_analysis(args):
    """Run G-Score distribution analysis across all stocks."""
    from strategist.g_score.calculator import compute_g_score_for_stocks
    from strategist.g_score.screener import load_pb_data

    # Get trade date
    from config.db import execute_query
    if args.date is None:
        rows = execute_query(
            "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily",
            env=args.env,
        )
        trade_date = str(rows[0]['max_date'])
    else:
        trade_date = args.date

    logger.info(f"[ANALYSIS] Analyzing G-Score distribution for {trade_date}")

    # Load all stocks with PB data
    pb_df = load_pb_data(trade_date, env=args.env)
    if pb_df.empty:
        print("No PB data available")
        return

    all_codes = pb_df['stock_code'].tolist()

    # Compute G-Score
    g_score_df = compute_g_score_for_stocks(all_codes, env=args.env)
    if g_score_df.empty:
        print("No G-Score data computed")
        return

    # Merge with PB
    merged = g_score_df.merge(pb_df[['stock_code', 'pb']], on='stock_code', how='inner')

    print(f"\n{'='*60}")
    print(f"G-Score Distribution Analysis ({trade_date})")
    print(f"{'='*60}")
    print(f"Total stocks with G-Score: {len(merged)}")

    # Overall distribution
    print("\n--- Overall G-Score Distribution ---")
    dist = merged['g_score'].value_counts().sort_index()
    for score, count in dist.items():
        pct = count / len(merged) * 100
        bar = '#' * int(pct)
        print(f"  G-Score {int(score)}: {count:5d} ({pct:5.1f}%) {bar}")

    # By PB group (high/medium/low)
    pb_70 = merged['pb'].quantile(0.70)
    pb_30 = merged['pb'].quantile(0.30)

    high_pb = merged[merged['pb'] >= pb_70]
    mid_pb = merged[(merged['pb'] >= pb_30) & (merged['pb'] < pb_70)]
    low_pb = merged[merged['pb'] < pb_30]

    print("\n--- By Valuation Group ---")
    print(f"  PB >= {pb_70:.2f} (High): {len(high_pb)} stocks, "
          f"avg G-Score: {high_pb['g_score'].mean():.2f}")
    print(f"  PB {pb_30:.2f} ~ {pb_70:.2f} (Mid): {len(mid_pb)} stocks, "
          f"avg G-Score: {mid_pb['g_score'].mean():.2f}")
    print(f"  PB < {pb_30:.2f} (Low): {len(low_pb)} stocks, "
          f"avg G-Score: {low_pb['g_score'].mean():.2f}")

    # Mohanram groups
    low_g = merged[merged['g_score'] <= 1]
    mid_g = merged[(merged['g_score'] >= 2) & (merged['g_score'] <= 5)]
    high_g = merged[merged['g_score'] >= 6]

    print("\n--- Mohanram Groups ---")
    print(f"  Low G-Score (0-1): {len(low_g)} stocks ({len(low_g)/len(merged)*100:.1f}%)")
    print(f"  Mid G-Score (2-5): {len(mid_g)} stocks ({len(mid_g)/len(merged)*100:.1f}%)")
    print(f"  High G-Score (6-8): {len(high_g)} stocks ({len(high_g)/len(merged)*100:.1f}%)")

    # Indicator coverage
    print("\n--- Indicator Coverage ---")
    score_indicators = {
        's_roa': 'ROA',
        's_cfoa': 'CFOA',
        's_accrual': 'Accrual',
        's_rd': 'R&D/Assets',
        's_sga': 'SGA/Assets',
        's_capex': 'Capex/Assets',
        's_roa_var': 'ROA Var',
        's_rev_var': 'Rev Growth Var',
    }
    for col, label in score_indicators.items():
        if col in merged.columns:
            scored_1 = (merged[col] == 1).sum()
            coverage = merged[col].notna().sum()
            print(f"  {label:15s}: {scored_1}/{len(merged)} scored 1 "
                  f"({coverage/len(merged)*100:.1f}% coverage)")


def main():
    parser = argparse.ArgumentParser(description='G-Score Strategy')
    parser.add_argument('--date', type=str, default=None, help='Trade date YYYY-MM-DD')
    parser.add_argument('--top-n', type=int, default=30, help='Max stocks to select')
    parser.add_argument('--min-score', type=int, default=5, help='Min G-Score threshold')
    parser.add_argument('--pb-percentile', type=int, default=70, help='PB percentile for high valuation')
    parser.add_argument('--env', type=str, default='online', help='Database environment')
    parser.add_argument('--output', type=str, default=None, help='Output CSV filename')
    parser.add_argument('--analyze', action='store_true', help='Run distribution analysis instead of screener')

    args = parser.parse_args()

    if args.analyze:
        run_analysis(args)
    else:
        run_screener(args)


if __name__ == '__main__':
    main()
