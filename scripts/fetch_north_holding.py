# -*- coding: utf-8 -*-
"""
scripts/fetch_north_holding.py

补充 trade_north_holding 沪深港通（北向资金）个股持仓数据（AKShare 接口）

字段说明：
  hold_amount  - 持股数量（股）
  hold_ratio   - 持股比例（%）
  hold_change  - 较上日持股变化（股）
  hold_value   - 持股市值（元）

数据来源：AKShare ak.stock_hsgt_individual_em（沪深港通个股资金流向）
或 ak.stock_hk_ggt_components_em

用法：
  DB_ENV=online python scripts/fetch_north_holding.py
  DB_ENV=online python scripts/fetch_north_holding.py --start 2024-01-01
  DB_ENV=online python scripts/fetch_north_holding.py --stock 000807
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


def get_latest_dates() -> dict[str, str]:
    rows = execute_query(
        "SELECT stock_code, MAX(hold_date) AS max_date FROM trade_north_holding GROUP BY stock_code",
        env=DB_ENV,
    )
    return {r["stock_code"]: str(r["max_date"]) for r in rows if r["max_date"]}


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
# Strategy 1: Per-date bulk fetch (recommended for initial load)
# ---------------------------------------------------------------------------

def fetch_by_date(trade_date: str) -> int:
    """
    Fetch north-bound holding for all stocks on a given date.
    AKShare: ak.stock_hsgt_individual_em(symbol="沪股通"|"深股通", start_date=..., end_date=...)
    Returns rows inserted.
    """
    date_fmt = trade_date.replace("-", "")
    all_rows = []

    for channel in ["沪股通", "深股通"]:
        fn = getattr(ak, "stock_hsgt_individual_em", None)
        if fn is None:
            logger.debug("stock_hsgt_individual_em not available")
            break
        try:
            df = fn(symbol=channel, start_date=date_fmt, end_date=date_fmt)
        except Exception as e:
            logger.debug(f"[{trade_date}] {channel} failed: {e}")
            time.sleep(0.5)
            continue

        if df is None or df.empty:
            time.sleep(0.3)
            continue

        df.columns = [str(c).strip() for c in df.columns]
        col_map = {
            "股票代码": "raw_code",
            "代码": "raw_code",
            "日期": "hold_date",
            "持股数量": "hold_amount",
            "持股市值": "hold_value",
            "持股占A股百分比": "hold_ratio",
            "持股变化数量": "hold_change",
            "增持": "hold_change_alt",
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

        if "raw_code" not in df.columns:
            logger.debug(f"[{trade_date}] {channel}: no code column. Cols: {list(df.columns)}")
            time.sleep(0.3)
            continue

        suffix = ".SH" if channel == "沪股通" else ".SZ"
        for _, row in df.iterrows():
            bare = str(row.get("raw_code", "")).strip().zfill(6)
            if not bare:
                continue
            stock_code = bare + suffix
            hold_change = _safe_float(row.get("hold_change", row.get("hold_change_alt", 0)))
            all_rows.append((
                stock_code,
                trade_date,
                _safe_float(row.get("hold_amount")),
                _safe_float(row.get("hold_ratio")),
                hold_change,
                _safe_float(row.get("hold_value")),
            ))

        time.sleep(0.4)

    if not all_rows:
        return 0

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
    try:
        execute_many(sql, all_rows, env=DB_ENV)
        return len(all_rows)
    except Exception as e:
        logger.error(f"[{trade_date}] DB insert failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Strategy 2: Per-stock fetch (for targeted updates or single stock test)
# ---------------------------------------------------------------------------

def fetch_one_stock(stock_code: str, start_date: str) -> int:
    """
    Fetch northbound holding history for a single stock.
    AKShare: ak.stock_hsgt_stock_statistics_em(symbol=code, start_date=..., end_date=...)
    """
    bare = _strip_suffix(stock_code)
    end_fmt = datetime.now().strftime("%Y%m%d")
    start_fmt = start_date.replace("-", "")

    fn = getattr(ak, "stock_hsgt_stock_statistics_em", None)
    if fn is None:
        return 0

    try:
        df = fn(symbol=bare, start_date=start_fmt, end_date=end_fmt)
    except Exception as e:
        logger.debug(f"[{stock_code}] stock_hsgt_stock_statistics_em failed: {e}")
        return 0

    if df is None or df.empty:
        return 0

    df.columns = [str(c).strip() for c in df.columns]
    col_map = {
        "日期": "hold_date",
        "持股数量": "hold_amount",
        "持股市值": "hold_value",
        "持股比例": "hold_ratio",
        "增持": "hold_change",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    if "hold_date" not in df.columns:
        return 0

    df["hold_date"] = df["hold_date"].astype(str).str[:10]
    df = df[df["hold_date"] >= start_date].copy()
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        rows.append((
            stock_code,
            row["hold_date"],
            _safe_float(row.get("hold_amount")),
            _safe_float(row.get("hold_ratio")),
            _safe_float(row.get("hold_change")),
            _safe_float(row.get("hold_value")),
        ))

    if not rows:
        return 0

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
    try:
        execute_many(sql, rows, env=DB_ENV)
        return len(rows)
    except Exception as e:
        logger.error(f"[{stock_code}] DB insert failed: {e}")
        return 0


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

    logger.info(f"DB_ENV={DB_ENV}, start={args.start}")
    end_date = args.end or datetime.now().strftime("%Y-%m-%d")

    if args.stock:
        latest = get_latest_dates()
        code = args.stock
        if "." not in code:
            code = code + (".SH" if code.startswith("6") else ".SZ")
        start = args.start
        if code in latest:
            last = datetime.strptime(latest[code], "%Y-%m-%d")
            start = (last + timedelta(days=1)).strftime("%Y-%m-%d")
        n = fetch_one_stock(code, start)
        logger.info(f"Done. Inserted {n} rows for {code}")
        return

    # By-date mode (default for bulk load)
    dates = get_trading_dates(args.start, end_date)
    logger.info(f"Trading dates to process: {len(dates)}")

    total = 0
    for i, d in enumerate(dates):
        n = fetch_by_date(d)
        total += n
        if i % 20 == 0:
            logger.info(f"Progress: {i}/{len(dates)} dates, total rows={total}")

    logger.info(f"Done. Total rows inserted: {total}")


if __name__ == "__main__":
    main()
