# -*- coding: utf-8 -*-
"""
Adapter functions for modules that don't have a simple zero-argument entry point.

Each adapter provides a `dry_run` parameter. When dry_run=True, only prints
what would happen without actually executing.
"""
import logging

logger = logging.getLogger(__name__)


def run_log_bias(dry_run: bool = False):
    """Adapter for strategist.log_bias.run_daily.run_daily."""
    if dry_run:
        logger.info("[DRY-RUN] run_log_bias: would run LogBias daily signal detection")
        return

    from strategist.log_bias.config import LogBiasConfig
    from strategist.log_bias.run_daily import run_daily

    config = LogBiasConfig()
    run_daily(config)


def run_technical_indicator_scan(dry_run: bool = False):
    """Adapter for data_analyst.indicators.technical.TechnicalIndicatorCalculator."""
    if dry_run:
        logger.info("[DRY-RUN] run_technical_indicator_scan: would calculate technical indicators for all stocks")
        return

    from data_analyst.indicators.technical import TechnicalIndicatorCalculator

    calculator = TechnicalIndicatorCalculator()
    calculator.calculate_for_all_stocks()


def run_paper_trading_settle(dry_run: bool = False):
    """Adapter for paper trading settlement."""
    if dry_run:
        logger.info("[DRY-RUN] run_paper_trading_settle: would settle paper trading positions")
        return

    # PaperTradingScheduler is not yet implemented; placeholder
    logger.info("[WARN] Paper trading settlement not yet implemented")


def run_industry_update(dry_run: bool = False):
    """Adapter for strategist.multi_factor.industry_fetcher."""
    if dry_run:
        logger.info("[DRY-RUN] run_industry_update: would fetch and update industry classifications")
        return

    from strategist.multi_factor.industry_fetcher import fetch_all_industries, update_db

    industry_map = fetch_all_industries()
    update_db(industry_map, dry_run=False)
    logger.info("Updated industry classifications for %d stocks", len(industry_map))
