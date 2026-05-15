# -*- coding: utf-8 -*-
"""
CLI entry point for Expectation Gap screener.

Usage:
    # Run for latest trade date
    python -m strategist.expectation_gap.run_screener

    # Run for specific trade date
    python -m strategist.expectation_gap.run_screener --trade-date 2026-05-12

    # Run with online database
    DB_ENV=online python -m strategist.expectation_gap.run_screener
"""

import argparse
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Expectation Gap Screener')
    parser.add_argument('--trade-date', type=str, default=None,
                        help='Trade date YYYY-MM-DD (default: latest)')
    parser.add_argument('--top-n', type=int, default=30,
                        help='Top N stocks per group (default: 30)')
    parser.add_argument('--env', type=str, default=None,
                        help='Database environment (default: from DB_ENV)')
    args = parser.parse_args()

    env = args.env or os.environ.get('DB_ENV', 'local')

    from strategist.expectation_gap.screener import screen_expectation_gap
    undervalued, overvalued = screen_expectation_gap(
        trade_date=args.trade_date,
        top_n=args.top_n,
        env=env,
    )

    print("\n" + "=" * 70)
    print("[UNDERVALUED] Low PB + High F-Score (market underestimates quality)")
    print("=" * 70)
    if undervalued.empty:
        print("  (none)")
    else:
        for _, row in undervalued.iterrows():
            print(f"  {row['stock_code']} {row['stock_name']:<8s} "
                  f"F={row['f_score']}/9 PB={row.get('pb', 0):.1f} "
                  f"PE={row.get('pe_ttm', 0):.1f} MV={row.get('total_mv', 0):.0f} "
                  f"Ind={row.get('industry', '-')}")

    print("\n" + "=" * 70)
    print("[OVERVALUED] High PB + Low F-Score (market overestimates quality)")
    print("=" * 70)
    if overvalued.empty:
        print("  (none)")
    else:
        for _, row in overvalued.iterrows():
            print(f"  {row['stock_code']} {row['stock_name']:<8s} "
                  f"F={row['f_score']}/9 PB={row.get('pb', 0):.1f} "
                  f"PE={row.get('pe_ttm', 0):.1f} MV={row.get('total_mv', 0):.0f} "
                  f"Ind={row.get('industry', '-')}")

    total = len(undervalued) + len(overvalued)
    print(f"\nTotal: {len(undervalued)} undervalued + {len(overvalued)} overvalued = {total}")


if __name__ == '__main__':
    main()
