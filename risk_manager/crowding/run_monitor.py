# -*- coding: utf-8 -*-
"""
拥挤度监控 - 主入口

Usage:
  python -m risk_manager.crowding.run_monitor --latest
  python -m risk_manager.crowding.run_monitor --start 2025-01-01 --end 2026-04-20
"""
import sys
import os
import argparse
import logging
from datetime import date, timedelta

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from risk_manager.crowding.config import CrowdingConfig
from risk_manager.crowding.data_loader import CrowdingDataLoader
from risk_manager.crowding.hhi_engine import HHIEngine
from risk_manager.crowding.crowding_scorer import CrowdingScorer
from risk_manager.crowding.storage import CrowdingStorage
from risk_manager.crowding.reporter import generate_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CrowdingMonitor:
    """拥挤度监控器"""

    def __init__(self, config: CrowdingConfig = None, env: str = 'online'):
        self.config = config or CrowdingConfig()
        self.loader = CrowdingDataLoader(env=env)
        self.hhi_engine = HHIEngine(self.config)
        self.scorer = CrowdingScorer(self.config)

    def run(self, start_date: str, end_date: str = None,
            save_db: bool = True, do_report: bool = True) -> dict:
        """
        Run crowding monitor.

        Args:
            start_date: Start date (YYYY-MM-DD) for output
            end_date: End date
            save_db: Save to DB
            do_report: Generate report

        Returns:
            dict with keys: scores, latest_level, report_path
        """
        if end_date is None:
            end_date = date.today().strftime('%Y-%m-%d')

        logger.info("=" * 60)
        logger.info(f"Crowding Monitor: {start_date} ~ {end_date}")
        logger.info("=" * 60)

        # Need lookback for HHI percentile calculation
        lookback_days = self.config.percentile_lookback + self.config.hhi_rolling_window + 30
        lookback_start = (pd.Timestamp(start_date) - timedelta(days=int(lookback_days * 1.5))).strftime('%Y-%m-%d')

        # 1. Init DB
        if save_db:
            try:
                CrowdingStorage.init_table()
            except Exception as e:
                logger.warning(f"DB init failed, skipping save: {e}")
                save_db = False

        # 2. Load data
        logger.info("[1/4] Loading turnover data...")
        turnover_df = self.loader.load_daily_turnover(lookback_start, end_date)
        logger.info(f"  Turnover: {len(turnover_df)} rows")

        logger.info("[2/4] Loading northbound & SVD data...")
        north_df = self.loader.load_northbound_flow(lookback_start, end_date)
        svd_df = self.loader.load_svd_state(lookback_start, end_date)
        logger.info(f"  Northbound: {len(north_df)} rows, SVD: {len(svd_df)} rows")

        # 3. Compute HHI
        logger.info("[3/4] Computing HHI...")
        hhi_daily = self.hhi_engine.compute_daily_hhi(turnover_df)
        hhi_rolling = self.hhi_engine.compute_rolling_hhi(hhi_daily)
        logger.info(f"  HHI computed: {len(hhi_rolling)} days")

        # 4. Compute crowding scores
        logger.info("[4/4] Computing crowding scores...")
        scores = self.scorer.compute_scores(hhi_rolling, north_df, svd_df, start_date)

        if not scores:
            logger.warning("No crowding scores computed")
            return {'scores': [], 'latest_level': None, 'report_path': None}

        latest = scores[-1]
        logger.info(f"Latest: score={latest.crowding_score}, level={latest.crowding_level} @ {latest.calc_date}")

        # Save & report
        if save_db:
            CrowdingStorage.save_batch(scores)

        report_path = None
        if do_report:
            output_dir = os.path.join(_PROJECT_ROOT, self.config.output_dir)
            report_path = generate_report(scores, output_dir)

        return {
            'scores': scores,
            'latest_level': latest.crowding_level,
            'report_path': report_path,
        }


def main():
    parser = argparse.ArgumentParser(description='Crowding Monitor')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--latest', action='store_true', help='Run for last 90 days')
    parser.add_argument('--no-db', action='store_true', help='Skip DB save')
    parser.add_argument('--no-report', action='store_true', help='Skip report')
    parser.add_argument('--env', type=str, default='online', help='DB environment')
    args = parser.parse_args()

    if args.latest:
        start_date = (date.today() - timedelta(days=90)).strftime('%Y-%m-%d')
    elif args.start:
        start_date = args.start
    else:
        start_date = (date.today() - timedelta(days=90)).strftime('%Y-%m-%d')

    monitor = CrowdingMonitor(env=args.env)
    result = monitor.run(
        start_date=start_date,
        end_date=args.end,
        save_db=not args.no_db,
        do_report=not args.no_report,
    )

    if result['latest_level']:
        print(f"\n[RESULT] Latest crowding level: {result['latest_level']}")
        print(f"[RESULT] Total scores: {len(result['scores'])}")
        if result['report_path']:
            print(f"[RESULT] Report: {result['report_path']}")


if __name__ == '__main__':
    main()
