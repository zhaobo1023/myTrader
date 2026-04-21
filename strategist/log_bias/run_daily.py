# -*- coding: utf-8 -*-
"""CLI entry point for log bias daily monitoring"""

import argparse
import logging
import os
import sys
from datetime import datetime
from datetime import timedelta

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from strategist.log_bias.config import LogBiasConfig
from strategist.log_bias.config import DEFAULT_ETFS
from strategist.log_bias.calculator import calculate_log_bias
from strategist.log_bias.signal_detector import SignalDetector
from strategist.log_bias.data_loader import DataLoader
from strategist.log_bias.data_loader import IndexDataLoader
from strategist.log_bias.storage import LogBiasStorage
from strategist.log_bias.report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('log_bias')


def run_daily(config: LogBiasConfig, target_date: str = None):
    """
    run daily log bias calculation for all tracked ETFs

    Args:
        config: LogBiasConfig
        target_date: target date string (YYYY-MM-DD), None = use latest trade date
    """
    logger.info("=" * 60)
    logger.info("Start log bias daily calculation")
    logger.info("=" * 60)

    # init
    loader = DataLoader(env=config.db_env)
    storage = LogBiasStorage(env=config.db_env)
    detector = SignalDetector(
        cooldown_days=config.cooldown_days,
        breakout_threshold=config.breakout_threshold,
        overheat_threshold=config.overheat_threshold,
        stall_threshold=config.stall_threshold,
    )
    generator = ReportGenerator(output_dir=config.output_dir, etf_names=config.etfs)

    storage.init_table()

    # determine target date
    if target_date:
        report_date = target_date
    else:
        latest = loader.get_latest_trade_date()
        report_date = latest
        if not latest:
            logger.error("Cannot determine latest trade date")
            return

    logger.info(f"Report date: {report_date}")
    logger.info(f"Tracking {len(config.etfs)} ETFs")

    summary_data = []
    for ts_code, name in config.etfs.items():
        try:
            df = loader.load(ts_code, lookback_days=config.lookback_days)
            if df.empty:
                logger.warning(f"No data for {ts_code} ({name})")
                continue

            result = calculate_log_bias(df, window=config.ema_window)
            signals = detector.detect_all(result)

            # save to db
            storage.save(ts_code, signals)

            # get the row for report_date
            signals['trade_date_str'] = pd.to_datetime(signals['trade_date']).dt.strftime('%Y-%m-%d')
            row = signals[signals['trade_date_str'] == report_date]
            if row.empty:
                # use last row if target date not found
                row = signals.tail(1)

            if not row.empty:
                r = row.iloc[0]
                summary_data.append({
                    'ts_code': ts_code,
                    'name': name,
                    'close': r['close'],
                    'log_bias': r['log_bias'],
                    'signal_state': r['signal_state'],
                    'prev_state': r['prev_state'],
                })
                logger.info(f"  {name} ({ts_code}): log_bias={r['log_bias']:.2f}, state={r['signal_state']}")

        except Exception as e:
            logger.error(f"Error processing {ts_code} ({name}): {e}")

    # generate report
    if summary_data:
        report_path = generator.generate(summary_data, report_date)
        if report_path:
            logger.info(f"Report: {report_path}")
    else:
        logger.warning("No data for report")

    logger.info("=" * 60)
    logger.info("Done")
    logger.info("=" * 60)


def run_daily_indices(config: LogBiasConfig):
    """
    Run daily log bias calculation for all tracked CSI thematic indices.
    Uses AKShare to fetch data (no DB dependency for price data).
    """
    logger.info("=" * 60)
    logger.info("Start CSI index log bias calculation")
    logger.info(f"Tracking {len(config.csi_indices)} CSI indices")
    logger.info("=" * 60)

    loader = IndexDataLoader(delay=0.3)
    storage = LogBiasStorage(env=config.db_env)
    detector = SignalDetector(
        cooldown_days=config.cooldown_days,
        breakout_threshold=config.breakout_threshold,
        overheat_threshold=config.overheat_threshold,
        stall_threshold=config.stall_threshold,
    )
    storage.init_table()

    ok_count = 0
    fail_count = 0
    for code, name in config.csi_indices.items():
        try:
            df = loader.load(code, lookback_days=config.lookback_days)
            if df.empty:
                logger.warning(f"No data for {code} ({name})")
                fail_count += 1
                continue

            result = calculate_log_bias(df, window=config.ema_window)
            signals = detector.detect_all(result)
            storage.save(code, signals)

            latest = signals.iloc[-1]
            logger.info(
                f"  {name} ({code}): log_bias={latest['log_bias']:.2f}, "
                f"state={latest['signal_state']}"
            )
            ok_count += 1
        except Exception as e:
            logger.error(f"Error processing {code} ({name}): {e}")
            fail_count += 1

    logger.info("=" * 60)
    logger.info(f"Done: {ok_count} OK, {fail_count} failed")
    logger.info("=" * 60)
    return ok_count


def main():
    parser = argparse.ArgumentParser(description='Log Bias Daily Monitor')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'])
    parser.add_argument('--output', type=str, help='Output directory for report')
    parser.add_argument('--mode', type=str, default='etf',
                        choices=['etf', 'index', 'all'],
                        help='etf=ETFs only, index=CSI indices only, all=both')

    args = parser.parse_args()

    config = LogBiasConfig()
    if args.env:
        config.db_env = args.env
    if args.output:
        config.output_dir = args.output

    try:
        if args.mode in ('etf', 'all'):
            run_daily(config, target_date=args.date)
        if args.mode in ('index', 'all'):
            run_daily_indices(config)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
