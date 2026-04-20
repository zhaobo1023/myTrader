# -*- coding: utf-8 -*-
"""
牛熊三指标监控 - 主入口

Usage:
  python -m data_analyst.bull_bear_monitor.run_monitor --latest
  python -m data_analyst.bull_bear_monitor.run_monitor --start 2024-06-01
  python -m data_analyst.bull_bear_monitor.run_monitor --start 2024-06-01 --end 2026-04-20 --no-db
"""
import sys
import os
import argparse
import logging
from datetime import date, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data_analyst.bull_bear_monitor.config import BullBearConfig
from data_analyst.bull_bear_monitor.data_loader import BullBearDataLoader
from data_analyst.bull_bear_monitor.indicator_engine import IndicatorEngine
from data_analyst.bull_bear_monitor.regime_judge import RegimeJudge
from data_analyst.bull_bear_monitor.storage import BullBearStorage
from data_analyst.bull_bear_monitor.reporter import generate_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BullBearMonitor:
    """牛熊三指标监控器"""

    def __init__(self, config: BullBearConfig = None, env: str = 'online'):
        self.config = config or BullBearConfig()
        self.loader = BullBearDataLoader(env=env)
        self.engine = IndicatorEngine(self.config)
        self.judge = RegimeJudge(self.config)

    def run(self, start_date: str, end_date: str = None,
            save_db: bool = True, do_report: bool = True) -> dict:
        """
        Run bull/bear regime monitor.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date, defaults to today
            save_db: Whether to save to DB
            do_report: Whether to generate report

        Returns:
            dict with keys: signals, latest_regime, report_path
        """
        if end_date is None:
            end_date = date.today().strftime('%Y-%m-%d')

        logger.info("=" * 60)
        logger.info(f"Bull/Bear Monitor: {start_date} ~ {end_date}")
        logger.info("=" * 60)

        # 1. Init DB table
        if save_db:
            try:
                BullBearStorage.init_table()
            except Exception as e:
                logger.warning(f"DB init failed, skipping save: {e}")
                save_db = False

        # 2. Load data
        logger.info("[1/4] Loading macro data...")
        data = self.loader.load_all_indicators(start_date, end_date, self.config)

        for key, df in data.items():
            logger.info(f"  {key}: {len(df)} rows")

        # 3. Compute signals
        logger.info("[2/4] Computing indicator signals...")
        bond_signals = self.engine.compute_bond_signal(data['bond'])
        usdcny_signals = self.engine.compute_usdcny_signal(data['usdcny'])
        dividend_signals = self.engine.compute_dividend_signal(data['dividend'], data['csi300'])

        # 4. Judge regime
        logger.info("[3/4] Judging regime...")
        signals = self.judge.judge(bond_signals, usdcny_signals, dividend_signals, start_date)

        if not signals:
            logger.warning("No signals generated - insufficient data")
            return {'signals': [], 'latest_regime': None, 'report_path': None}

        latest = signals[-1]
        logger.info(f"Latest regime: {latest.regime} (score={latest.composite_score}) @ {latest.calc_date}")

        # 5. Save & report
        if save_db:
            logger.info("[4/4] Saving to DB...")
            BullBearStorage.save_batch(signals)

        report_path = None
        if do_report:
            output_dir = os.path.join(_PROJECT_ROOT, self.config.output_dir)
            report_path = generate_report(signals, output_dir)

        return {
            'signals': signals,
            'latest_regime': latest.regime,
            'report_path': report_path,
        }


def main():
    parser = argparse.ArgumentParser(description='Bull/Bear Three-Indicator Monitor')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--latest', action='store_true', help='Run for last 365 days')
    parser.add_argument('--no-db', action='store_true', help='Skip DB save')
    parser.add_argument('--no-report', action='store_true', help='Skip report generation')
    parser.add_argument('--env', type=str, default='online', help='DB environment')
    args = parser.parse_args()

    if args.latest:
        start_date = (date.today() - timedelta(days=365)).strftime('%Y-%m-%d')
    elif args.start:
        start_date = args.start
    else:
        start_date = (date.today() - timedelta(days=365)).strftime('%Y-%m-%d')

    monitor = BullBearMonitor(env=args.env)
    result = monitor.run(
        start_date=start_date,
        end_date=args.end,
        save_db=not args.no_db,
        do_report=not args.no_report,
    )

    if result['latest_regime']:
        print(f"\n[RESULT] Latest regime: {result['latest_regime']}")
        print(f"[RESULT] Total signals: {len(result['signals'])}")
        if result['report_path']:
            print(f"[RESULT] Report: {result['report_path']}")


if __name__ == '__main__':
    main()
