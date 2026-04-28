# -*- coding: utf-8 -*-
"""
scripts/fetch_margin.py

trade_margin_trade (AKShare)

:
  rzye   -
  rqye   -
  rzmre  -
  rzche  -
  rqmcl  -
  rqchl  -

:
  AKShare ak.stock_margin_detail_sse(date=...) -- SSE (SH)
  AKShare ak.stock_margin_detail_szse(date=...) -- SZSE (SZ)
  date

:
  DB_ENV=online python scripts/fetch_margin.py
  DB_ENV=online python scripts/fetch_margin.py --start 2024-01-01
  DB_ENV=online python scripts/fetch_margin.py --start 2026-01-01 --end 2026-04-28
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

def _safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def get_latest_date() -> str:
    """Return the latest trade_date in trade_margin_trade, or empty string."""
    rows = execute_query(
        "SELECT MAX(trade_date) AS max_date FROM trade_margin_trade",
        env=DB_ENV,
    )
    if rows and rows[0]["max_date"]:
        return str(rows[0]["max_date"])
    return ""


def get_trading_dates(start: str, end: str) -> list[str]:
    """Get trading dates from trade_stock_daily_basic."""
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
# Fetch one day (SSE + SZSE)
# ---------------------------------------------------------------------------

def fetch_one_day(trade_date: str) -> int:
    """
    Fetch margin trade data for all stocks on a given date.
    Uses ak.stock_margin_detail_sse(date=YYYYMMDD) for SH stocks
    and ak.stock_margin_detail_szse(date=YYYYMMDD) for SZ stocks.
    Returns number of rows inserted.
    """
    date_fmt = trade_date.replace("-", "")
    day_rows = []

    # --- SSE (SH) ---
    # Columns: 信用交易日期, 标的证券代码, 标的证券简称, 融资余额, 融资买入额, 融资偿还额, 融券余量, 融券卖出量, 融券偿还量
    try:
        df_sh = ak.stock_margin_detail_sse(date=date_fmt)
        if df_sh is not None and not df_sh.empty:
            df_sh.columns = [str(c).strip() for c in df_sh.columns]
            for _, row in df_sh.iterrows():
                bare = str(row.get("标的证券代码", "")).strip().zfill(6)
                if not bare or len(bare) != 6:
                    continue
                stock_code = bare + ".SH"
                day_rows.append((
                    stock_code,
                    trade_date,
                    _safe_float(row.get("融资余额")),
                    0.0,  # rqye: SSE detail does not have 融券余额, use 0
                    _safe_float(row.get("融资买入额")),
                    _safe_float(row.get("融资偿还额")),
                    _safe_float(row.get("融券卖出量")),
                    _safe_float(row.get("融券偿还量")),
                ))
    except Exception as e:
        logger.warning(f"[{trade_date}] stock_margin_detail_sse failed: {e}")
    time.sleep(0.3)

    # --- SZSE (SZ) ---
    # Columns: 证券代码, 证券简称, 融资买入额, 融资余额, 融券卖出量, 融券余量, 融券余额, 融资融券余额
    try:
        df_sz = ak.stock_margin_detail_szse(date=date_fmt)
        if df_sz is not None and not df_sz.empty:
            df_sz.columns = [str(c).strip() for c in df_sz.columns]
            for _, row in df_sz.iterrows():
                bare = str(row.get("证券代码", "")).strip().zfill(6)
                if not bare or len(bare) != 6:
                    continue
                stock_code = bare + ".SZ"
                day_rows.append((
                    stock_code,
                    trade_date,
                    _safe_float(row.get("融资余额")),
                    _safe_float(row.get("融券余额")),
                    _safe_float(row.get("融资买入额")),
                    0.0,  # rzche: SZSE detail does not have 融资偿还额
                    _safe_float(row.get("融券卖出量")),
                    0.0,  # rqchl: SZSE detail does not have 融券偿还量
                ))
    except Exception as e:
        logger.warning(f"[{trade_date}] stock_margin_detail_szse failed: {e}")
    time.sleep(0.3)

    if not day_rows:
        return 0

    sql = """
        INSERT INTO trade_margin_trade
            (stock_code, trade_date, rzye, rqye, rzmre, rzche, rqmcl, rqchl)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            rzye=VALUES(rzye), rqye=VALUES(rqye),
            rzmre=VALUES(rzmre), rzche=VALUES(rzche),
            rqmcl=VALUES(rqmcl), rqchl=VALUES(rqchl)
    """
    try:
        execute_many(sql, day_rows, env=DB_ENV)
        return len(day_rows)
    except Exception as e:
        logger.error(f"[{trade_date}] DB insert failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Batch fetch by date range
# ---------------------------------------------------------------------------

def fetch_by_date_range(start_date: str, end_date: str = None) -> int:
    """
    Iterate over trading dates and pull all margin data for each day.
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    dates = get_trading_dates(start_date, end_date)
    logger.info(f"Trading dates to process: {len(dates)}")

    total_inserted = 0
    for i, trade_date in enumerate(dates):
        n = fetch_one_day(trade_date)
        total_inserted += n
        if i % 20 == 0 or n > 0:
            logger.info(f"[{i+1}/{len(dates)}] {trade_date}: +{n} rows (total={total_inserted})")

    return total_inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch trade_margin_trade from AKShare")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--envs", default=os.getenv("DB_ENV", "online"),
                        help="Comma-separated DB envs (e.g. local,online)")
    parser.add_argument("--no-proxy", dest="no_proxy", action="store_true")
    parser.add_argument("--incremental", action="store_true",
                        help="Auto-detect start from last loaded date")
    # Keep --by-date for backward compatibility (now default behavior)
    parser.add_argument("--by-date", action="store_true",
                        help="(deprecated, now default) Fetch by date")
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

    logger.info(f"DB_ENV={DB_ENV}, start={start}, end={args.end or 'today'}")
    n = fetch_by_date_range(start, args.end)
    logger.info(f"Done. Total rows inserted: {n}")


if __name__ == "__main__":
    main()
