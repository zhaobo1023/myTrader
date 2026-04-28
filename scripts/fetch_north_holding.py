# -*- coding: utf-8 -*-
"""
scripts/fetch_north_holding.py

trade_north_holding (AKShare)

:
  hold_amount  -
  hold_ratio   - (%)
  hold_change  -
  hold_value   -

:
  AKShare ak.stock_hsgt_stock_statistics_em(symbol='北向持股', start_date, end_date)
  -- ,
  AKShare ak.stock_hsgt_individual_em(symbol=code)
  -- ,  ()

:
  DB_ENV=online python scripts/fetch_north_holding.py
  DB_ENV=online python scripts/fetch_north_holding.py --start 2024-01-01 --end 2024-08-16
  DB_ENV=online python scripts/fetch_north_holding.py --stock 600519
"""

import argparse
import os
import sys

_args_pre = sys.argv[1:]
if "--no-proxy" in _args_pre:
    for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                 "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        os.environ.pop(_var, None)
    os.environ["NO_PROXY"] = "*"

import logging
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_many

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

try:
    import akshare as ak
    import pandas as pd
except ImportError as e:
    logger.error(f"Missing package: {e}. Run: pip install akshare pandas")
    sys.exit(1)

DB_ENV = os.getenv("DB_ENV", "online")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_suffix(code: str) -> str:
    return code.split(".")[0]


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _normalize_code(bare: str) -> str:
    """Convert 6-digit code to exchange-suffixed format."""
    bare = str(bare).strip().zfill(6)
    if bare.startswith(('6', '9')):
        return bare + ".SH"
    elif bare.startswith(('0', '3')):
        return bare + ".SZ"
    elif bare.startswith(('4', '8')):
        return bare + ".BJ"
    return bare + ".SZ"


def get_latest_date() -> str:
    """Return the latest hold_date in trade_north_holding, or empty string."""
    rows = execute_query(
        "SELECT MAX(hold_date) AS max_date FROM trade_north_holding",
        env=DB_ENV,
    )
    if rows and rows[0]["max_date"]:
        return str(rows[0]["max_date"])
    return ""


def get_trading_dates(start: str, end: str) -> list[str]:
    rows = execute_query(
        """
        SELECT DISTINCT trade_date FROM trade_stock_daily_basic
        WHERE trade_date >= %s AND trade_date <= %s
        ORDER BY trade_date ASC
        """,
        [start, end],
        env=DB_ENV,
    )
    return [str(r["trade_date"]) for r in rows]


# ---------------------------------------------------------------------------
# Strategy 1: Bulk fetch by date range
#   ak.stock_hsgt_stock_statistics_em(symbol='北向持股', start_date, end_date)
#   Returns all stocks for a date range (efficient for batch load)
# ---------------------------------------------------------------------------

def fetch_by_date_range(start_date: str, end_date: str) -> int:
    """
    Bulk fetch using stock_hsgt_stock_statistics_em.
    Fetches in 1-day chunks to avoid API limits.
    """
    dates = get_trading_dates(start_date, end_date)
    logger.info(f"Trading dates to process: {len(dates)}")

    total = 0
    for i, trade_date in enumerate(dates):
        date_fmt = trade_date.replace("-", "")
        try:
            df = ak.stock_hsgt_stock_statistics_em(
                symbol="北向持股",
                start_date=date_fmt,
                end_date=date_fmt,
            )
        except Exception as e:
            logger.warning(f"[{trade_date}] stock_hsgt_stock_statistics_em failed: {e}")
            time.sleep(1)
            continue

        if df is None or df.empty:
            if i % 20 == 0:
                logger.info(f"[{i+1}/{len(dates)}] {trade_date}: no data")
            time.sleep(0.5)
            continue

        df.columns = [str(c).strip() for c in df.columns]
        # Columns: 持股日期, 股票代码, 股票简称, 当日收盘价, 当日涨跌幅,
        #          持股数量, 持股市值, 持股数量占发行股百分比,
        #          持股市值变化-1日, 持股市值变化-5日, 持股市值变化-10日

        rows = []
        for _, row in df.iterrows():
            bare = str(row.get("股票代码", "")).strip().zfill(6)
            if not bare or len(bare) != 6:
                continue
            stock_code = _normalize_code(bare)
            rows.append((
                stock_code,
                trade_date,
                _safe_float(row.get("持股数量")),
                _safe_float(row.get("持股数量占发行股百分比")),
                _safe_float(row.get("持股市值变化-1日")),  # hold_change as value change
                _safe_float(row.get("持股市值")),
            ))

        if rows:
            _upsert_rows(rows)
            total += len(rows)

        if i % 20 == 0 or len(rows) > 0:
            logger.info(f"[{i+1}/{len(dates)}] {trade_date}: +{len(rows)} rows (total={total})")

        time.sleep(0.5)

    return total


# ---------------------------------------------------------------------------
# Strategy 2: Per-stock fetch (for targeted updates)
#   ak.stock_hsgt_individual_em(symbol=bare_code)
#   Returns full history for one stock
# ---------------------------------------------------------------------------

def fetch_one_stock(stock_code: str, start_date: str = "2024-01-01") -> int:
    """Fetch northbound holding history for a single stock."""
    bare = _strip_suffix(stock_code)

    fn = getattr(ak, "stock_hsgt_individual_em", None)
    if fn is None:
        logger.warning("stock_hsgt_individual_em not available")
        return 0

    try:
        df = fn(symbol=bare)
    except Exception as e:
        logger.debug(f"[{stock_code}] stock_hsgt_individual_em failed: {e}")
        return 0

    if df is None or df.empty:
        return 0

    df.columns = [str(c).strip() for c in df.columns]
    # Columns: 持股日期, 当日收盘价, 当日涨跌幅, 持股数量, 持股市值,
    #          持股数量占A股百分比, 今日增持股数, 今日增持资金, 今日持股市值变化

    if "持股日期" not in df.columns:
        return 0

    df["持股日期"] = df["持股日期"].astype(str).str[:10]
    df = df[df["持股日期"] >= start_date].copy()
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        rows.append((
            stock_code,
            row["持股日期"],
            _safe_float(row.get("持股数量")),
            _safe_float(row.get("持股数量占A股百分比")),
            _safe_float(row.get("今日增持股数")),
            _safe_float(row.get("持股市值")),
        ))

    if rows:
        _upsert_rows(rows)

    return len(rows)


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

def _upsert_rows(rows: list[tuple]) -> None:
    sql = """
        INSERT INTO trade_north_holding
            (stock_code, hold_date, hold_amount, hold_ratio, hold_change, hold_value)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            hold_amount=VALUES(hold_amount),
            hold_ratio=VALUES(hold_ratio),
            hold_change=VALUES(hold_change),
            hold_value=VALUES(hold_value)
    """
    execute_many(sql, rows, env=DB_ENV)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch trade_north_holding from AKShare")
    parser.add_argument("--stock", help="Single stock code (triggers per-stock mode)")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--envs", default=os.getenv("DB_ENV", "online"),
                        help="Comma-separated DB envs (e.g. local,online)")
    parser.add_argument("--no-proxy", dest="no_proxy", action="store_true")
    parser.add_argument("--incremental", action="store_true",
                        help="Auto-detect start from last loaded date")
    args = parser.parse_args()

    global DB_ENV
    DB_ENV = args.envs.split(",")[0]

    start = args.start
    if args.incremental:
        latest = get_latest_date()
        if latest:
            last = datetime.strptime(latest, "%Y-%m-%d")
            start = (last + timedelta(days=1)).strftime("%Y-%m-%d")
            logger.info(f"Incremental mode: last date={latest}, starting from {start}")

    end_date = args.end or datetime.now().strftime("%Y-%m-%d")
    logger.info(f"DB_ENV={DB_ENV}, start={start}, end={end_date}")

    if args.stock:
        code = args.stock
        if "." not in code:
            code = _normalize_code(code)
        n = fetch_one_stock(code, start)
        logger.info(f"Done. Inserted {n} rows for {code}")
        return

    n = fetch_by_date_range(start, end_date)
    logger.info(f"Done. Total rows inserted: {n}")


if __name__ == "__main__":
    main()
