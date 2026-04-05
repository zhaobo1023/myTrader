# -*- coding: utf-8 -*-
"""
Readiness gate - polls the database until daily price data is available.

Replaces the fixed 18:00 schedule with a data-driven approach:
polls trade_stock_daily for the latest trade_date and compares
with the expected trade date.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

from config.db import execute_query

logger = logging.getLogger(__name__)


def get_latest_trade_date(env=None) -> Optional[str]:
    """
    Query the latest trade_date from trade_stock_daily.

    Returns:
        Date string (YYYY-MM-DD) or None if no data.
    """
    sql = "SELECT MAX(trade_date) AS latest FROM trade_stock_daily"
    rows = execute_query(sql, env=env)
    if rows and rows[0]["latest"]:
        return str(rows[0]["latest"])
    return None


def expected_trade_date() -> str:
    """
    Calculate the expected trade date based on current time.

    If it's a weekday before 17:00, expects today.
    If it's a weekday after 17:00 or weekend, expects the most recent weekday.
    Returns date string (YYYY-MM-DD).
    """
    now = datetime.now()

    # If weekend, go back to Friday
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        days_back = now.weekday() - 4  # 1 on Sat, 2 on Sun
        expected = now - timedelta(days=days_back)
        return expected.strftime("%Y-%m-%d")

    # Weekday: if before 17:00, expect today; after 17:00, expect today
    # (data should be available after market close ~15:30)
    return now.strftime("%Y-%m-%d")


def wait_for_daily_data(dry_run: bool = False, timeout_min: int = 60) -> bool:
    """
    Poll the database until the latest trade_date matches the expected date.

    Args:
        dry_run: If True, check once and return without polling.
        timeout_min: Maximum wait time in minutes.

    Returns:
        True if data is ready.

    Raises:
        TimeoutError: If data is not ready within the timeout period.
    """
    expected = expected_trade_date()
    logger.info("Waiting for daily data (expected=%s, timeout=%dmin, dry_run=%s)",
                 expected, timeout_min, dry_run)

    if dry_run:
        latest = get_latest_trade_date()
        if latest == expected:
            logger.info("[DRY-RUN] Data already up to date: %s", latest)
        else:
            logger.info("[DRY-RUN] Latest data: %s, expected: %s", latest, expected)
        return True

    start = time.time()
    timeout_s = timeout_min * 60
    poll_interval = 300  # 5 minutes

    while time.time() - start < timeout_s:
        latest = get_latest_trade_date()
        if latest == expected:
            logger.info("Data ready: %s", latest)
            return True

        elapsed = int(time.time() - start)
        remaining = int(timeout_s - elapsed)
        logger.info("Waiting... latest=%s, expected=%s, remaining=%ds",
                     latest, expected, remaining)
        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timed out after {timeout_min}min waiting for daily data "
        f"(expected={expected}, latest={get_latest_trade_date()})"
    )
