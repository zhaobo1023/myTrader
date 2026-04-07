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


# ---------------------------------------------------------------------------
# Data supplement adapters (daily incremental, dual-write local+online)
# ---------------------------------------------------------------------------

def _clear_proxy():
    """Remove proxy env vars so AKShare can reach external APIs directly."""
    import os
    for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                 "ALL_PROXY", "all_proxy"):
        os.environ.pop(_var, None)
    os.environ["NO_PROXY"] = "*"


def fetch_moneyflow_incremental(dry_run: bool = False, envs: str = "local,online"):
    """
    Daily incremental fetch of trade_stock_moneyflow.
    Writes to all envs in comma-separated envs string.
    """
    if dry_run:
        logger.info("[DRY-RUN] fetch_moneyflow_incremental: would fetch yesterday's moneyflow")
        return

    _clear_proxy()

    import sys
    import os
    import importlib.util
    sys.argv = ["fetch_moneyflow", "--incremental", "--no-proxy", "--envs", envs]

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fetch_moneyflow.py")
    spec = importlib.util.spec_from_file_location("fetch_moneyflow", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def fetch_sw_industry_sync(dry_run: bool = False, envs: str = "local,online"):
    """
    Sync SW industry classification from trade_stock_basic (fast, no API).
    Run weekly or after bulk stock list update.
    """
    if dry_run:
        logger.info("[DRY-RUN] fetch_sw_industry_sync: would sync industry classification")
        return

    from config.db import execute_query, execute_many

    env_list = [e.strip() for e in envs.split(",") if e.strip()]
    source_env = env_list[0]

    rows = execute_query(
        "SELECT stock_code, stock_name, industry FROM trade_stock_basic "
        "WHERE industry IS NOT NULL AND industry != ''",
        env=source_env,
    )
    if not rows:
        logger.warning("trade_stock_basic has no industry data")
        return

    data = [
        (r["stock_code"], r["stock_name"] or "", "", r["industry"], "1", "SW")
        for r in rows if r.get("industry")
    ]

    sql = """
        INSERT INTO trade_stock_industry
            (stock_code, stock_name, industry_code, industry_name, industry_level, classify_type)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE industry_name = VALUES(industry_name)
    """
    for env in env_list:
        try:
            execute_many(sql, data, env=env)
            logger.info(f"[env={env}] SW industry sync: {len(data)} rows")
        except Exception as e:
            logger.error(f"[env={env}] SW industry sync failed: {e}")


def fetch_margin_incremental(dry_run: bool = False, envs: str = "local,online"):
    """Daily incremental fetch of trade_margin_trade (by-date mode)."""
    if dry_run:
        logger.info("[DRY-RUN] fetch_margin_incremental: would fetch yesterday's margin data")
        return

    _clear_proxy()
    from datetime import datetime, timedelta

    import sys
    import os
    import importlib.util
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    sys.argv = ["fetch_margin", "--by-date", "--start", yesterday, "--no-proxy", "--envs", envs]

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fetch_margin.py")
    spec = importlib.util.spec_from_file_location("fetch_margin", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def fetch_north_holding_incremental(dry_run: bool = False, envs: str = "local,online"):
    """Daily incremental fetch of trade_north_holding."""
    if dry_run:
        logger.info("[DRY-RUN] fetch_north_holding_incremental: would fetch yesterday's north holding")
        return

    _clear_proxy()
    from datetime import datetime, timedelta

    import sys
    import os
    import importlib.util
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    sys.argv = ["fetch_north_holding", "--start", yesterday, "--no-proxy", "--envs", envs]

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fetch_north_holding.py")
    spec = importlib.util.spec_from_file_location("fetch_north_holding", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
