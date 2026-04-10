# -*- coding: utf-8 -*-
"""
scripts/fetch_margin.py

补充 trade_margin_trade 融资融券数据（AKShare 接口）

字段说明：
  rzye   - 融资余额（元）
  rqye   - 融券余额（元）
  rzmre  - 融资买入额（元）
  rzche  - 融资偿还额（元）
  rqmcl  - 融券卖出量（股）
  rqchl  - 融券偿还量（股）

数据来源：AKShare ak.stock_margin_detail_szse / ak.stock_margin_sse

用法：
  DB_ENV=online python scripts/fetch_margin.py
  DB_ENV=online python scripts/fetch_margin.py --stock 000807 --start 2024-01-01
  DB_ENV=online python scripts/fetch_margin.py --start 2023-01-01
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


def get_stock_list() -> list[dict]:
    return execute_query(
        "SELECT stock_code, stock_name FROM trade_stock_basic WHERE is_st = 0",
        env=DB_ENV,
    )


def get_latest_dates() -> dict[str, str]:
    rows = execute_query(
        "SELECT stock_code, MAX(trade_date) AS max_date FROM trade_margin_trade GROUP BY stock_code",
        env=DB_ENV,
    )
    return {r["stock_code"]: str(r["max_date"]) for r in rows if r["max_date"]}


# ---------------------------------------------------------------------------
# AKShare fetch (individual stock)
# ---------------------------------------------------------------------------

def fetch_one_margin(stock_code: str, start_date: str) -> int:
    """
    Fetch margin trade data for one stock.
    AKShare: ak.stock_margin_detail_szse(symbol=code, start_date=..., end_date=...)
             ak.stock_margin_sse(date=...) — by date, not by stock

    Use ak.stock_margin_detail_szse for SZ stocks and
    ak.stock_margin_detail_sse for SH stocks.
    """
    bare = _strip_suffix(stock_code)
    end_date = datetime.now().strftime("%Y%m%d")
    start_fmt = start_date.replace("-", "")

    # Determine exchange
    if stock_code.endswith(".SH") or bare.startswith("6"):
        fetch_fn_name = "stock_margin_detail_sse"
    else:
        fetch_fn_name = "stock_margin_detail_szse"

    fetch_fn = getattr(ak, fetch_fn_name, None)
    if fetch_fn is None:
        logger.debug(f"[{stock_code}] {fetch_fn_name} not available in this AKShare version")
        return 0

    try:
        df = fetch_fn(symbol=bare, start_date=start_fmt, end_date=end_date)
    except Exception as e:
        logger.debug(f"[{stock_code}] {fetch_fn_name} failed: {e}")
        return 0

    if df is None or df.empty:
        return 0

    df.columns = [str(c).strip() for c in df.columns]

    # Normalize columns (AKShare version-dependent)
    col_map = {
        "信用交易日期": "trade_date",
        "日期": "trade_date",
        "融资余额": "rzye",
        "融券余额": "rqye",
        "融资买入额": "rzmre",
        "融资偿还额": "rzche",
        "融券卖出量": "rqmcl",
        "融券偿还量": "rqchl",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    if "trade_date" not in df.columns:
        return 0

    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    df = df[df["trade_date"] >= start_date].copy()
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        rows.append((
            stock_code,
            row["trade_date"],
            _safe_float(row.get("rzye")),
            _safe_float(row.get("rqye")),
            _safe_float(row.get("rzmre")),
            _safe_float(row.get("rzche")),
            _safe_float(row.get("rqmcl")),
            _safe_float(row.get("rqchl")),
        ))

    if not rows:
        return 0

    sql = """
        INSERT INTO trade_margin_trade
            (stock_code, trade_date, rzye, rqye, rzmre, rzche, rqmcl, rqchl)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            rzye=VALUES(rzye), rqye=VALUES(rqye),
            rzmre=VALUES(rzmre), rzche=VALUES(rzche)
    """
    try:
        execute_many(sql, rows, env=DB_ENV)
        return len(rows)
    except Exception as e:
        logger.error(f"[{stock_code}] DB insert failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Batch by date (alternative approach: fetch all stocks for a given date)
# ---------------------------------------------------------------------------

def fetch_by_date_range(start_date: str, end_date: str = None) -> int:
    """
    Bulk fetch: iterate over each trading date and pull all margin data for that day.
    More efficient than per-stock for initial full load.
    AKShare: ak.stock_margin_szse(date=...) and ak.stock_margin_sse(date=...)
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # Get trading dates from our DB
    rows = execute_query(
        """
        SELECT DISTINCT trade_date FROM trade_stock_daily_basic
        WHERE trade_date >= %s AND trade_date <= %s
        ORDER BY trade_date ASC
        """,
        [start_date, end_date],
        env=DB_ENV,
    )
    dates = [str(r["trade_date"]) for r in rows]
    logger.info(f"Trading dates to process: {len(dates)}")

    total_inserted = 0

    for trade_date in dates:
        date_fmt = trade_date.replace("-", "")
        day_rows = []

        for exchange, fn_name in [("sz", "stock_margin_szse"), ("sh", "stock_margin_sse")]:
            fn = getattr(ak, fn_name, None)
            if fn is None:
                continue
            try:
                df = fn(date=date_fmt)
                if df is None or df.empty:
                    continue
                df.columns = [str(c).strip() for c in df.columns]
                col_map = {
                    "证券代码": "raw_code",
                    "代码": "raw_code",
                    "融资余额": "rzye",
                    "融券余额": "rqye",
                    "融资买入额": "rzmre",
                    "融资偿还额": "rzche",
                    "融券卖出量": "rqmcl",
                    "融券偿还量": "rqchl",
                }
                df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
                if "raw_code" not in df.columns:
                    continue

                suffix = ".SH" if exchange == "sh" else ".SZ"
                for _, row in df.iterrows():
                    bare = str(row["raw_code"]).strip().zfill(6)
                    stock_code = bare + suffix
                    day_rows.append((
                        stock_code,
                        trade_date,
                        _safe_float(row.get("rzye")),
                        _safe_float(row.get("rqye")),
                        _safe_float(row.get("rzmre")),
                        _safe_float(row.get("rzche")),
                        _safe_float(row.get("rqmcl")),
                        _safe_float(row.get("rqchl")),
                    ))
            except Exception as e:
                logger.debug(f"[{trade_date}] {fn_name} failed: {e}")
            time.sleep(0.3)

        if day_rows:
            sql = """
                INSERT INTO trade_margin_trade
                    (stock_code, trade_date, rzye, rqye, rzmre, rzche, rqmcl, rqchl)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    rzye=VALUES(rzye), rqye=VALUES(rqye),
                    rzmre=VALUES(rzmre), rzche=VALUES(rzche)
            """
            try:
                execute_many(sql, day_rows, env=DB_ENV)
                total_inserted += len(day_rows)
                logger.info(f"[{trade_date}] Inserted {len(day_rows)} rows (total={total_inserted})")
            except Exception as e:
                logger.error(f"[{trade_date}] DB insert failed: {e}")

    return total_inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch trade_margin_trade from AKShare")
    parser.add_argument("--stock", help="Single stock code")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--envs", default=os.getenv("DB_ENV", "online"),
                        help="Comma-separated DB envs (e.g. local,online)")
    parser.add_argument("--no-proxy", dest="no_proxy", action="store_true")
    parser.add_argument("--incremental", action="store_true",
                        help="Auto-detect start from last loaded date")
    parser.add_argument("--by-date", action="store_true",
                        help="Fetch by date (bulk) instead of per-stock")
    args = parser.parse_args()

    global DB_ENV
    DB_ENV = args.envs.split(",")[0]

    logger.info(f"DB_ENV={DB_ENV}, start={args.start}")

    if args.by_date:
        n = fetch_by_date_range(args.start, args.end)
        logger.info(f"Done (by-date). Total rows: {n}")
        return

    if args.stock:
        stocks = [{"stock_code": args.stock}]
    else:
        stocks = get_stock_list()

    latest_dates = get_latest_dates()
    total = 0
    for i, s in enumerate(stocks):
        code = s["stock_code"]
        if code in latest_dates:
            last = datetime.strptime(latest_dates[code], "%Y-%m-%d")
            effective_start = (last + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            effective_start = args.start

        if effective_start > datetime.now().strftime("%Y-%m-%d"):
            continue

        n = fetch_one_margin(code, effective_start)
        total += n
        if i % 100 == 0:
            logger.info(f"Progress: {i}/{len(stocks)}, inserted={total}")
        time.sleep(0.5)

    logger.info(f"Done. Total rows inserted: {total}")


if __name__ == "__main__":
    main()
