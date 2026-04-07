# -*- coding: utf-8 -*-
"""
scripts/fetch_moneyflow.py

补充 trade_stock_moneyflow 主力资金流向数据（AKShare 东方财富接口）

数据来源：AKShare ak.stock_individual_fund_flow
字段映射：
  超大单 + 大单净流入合计 -> net_mf_amount（主力净流入金额，元）

用法：
  # 全量拉取（增量写入 online）
  DB_ENV=online python scripts/fetch_moneyflow.py --no-proxy

  # 双写 local + online
  python scripts/fetch_moneyflow.py --envs local,online --no-proxy

  # 测试单只
  python scripts/fetch_moneyflow.py --stock 000807 --no-proxy

  # 指定日期范围
  python scripts/fetch_moneyflow.py --start 2024-01-01 --no-proxy --envs local,online

  # 日增量（加入调度器后的调用方式）
  python scripts/fetch_moneyflow.py --incremental --no-proxy --envs local,online
"""

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# Parse --no-proxy BEFORE any network library import so proxy is cleared early
# ---------------------------------------------------------------------------
_args_pre = [a for a in sys.argv[1:]]
if "--no-proxy" in _args_pre:
    for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                 "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        os.environ.pop(_var, None)
    os.environ["NO_PROXY"] = "*"

import logging
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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
except ImportError:
    logger.error("AKShare 未安装，请运行: pip install akshare")
    sys.exit(1)

REQUEST_DELAY = 0.8  # seconds between requests per thread


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_suffix(code: str) -> str:
    return code.split(".")[0]


def _market(code: str) -> str:
    prefix = _strip_suffix(code)
    if prefix.startswith("6"):
        return "sh"
    elif prefix.startswith(("0", "3", "2")):
        return "sz"
    elif prefix.startswith(("8", "4")):
        return "bj"
    return "sz"


def get_stock_list(env: str) -> list[dict]:
    return execute_query(
        "SELECT stock_code, stock_name FROM trade_stock_basic WHERE is_st = 0",
        env=env,
    )


def get_latest_dates(env: str) -> dict[str, str]:
    rows = execute_query(
        "SELECT stock_code, MAX(trade_date) AS max_date FROM trade_stock_moneyflow GROUP BY stock_code",
        env=env,
    )
    return {r["stock_code"]: str(r["max_date"]) for r in rows if r["max_date"]}


# ---------------------------------------------------------------------------
# AKShare fetch
# ---------------------------------------------------------------------------

def fetch_one(stock_code: str, start_date: str) -> list[tuple]:
    """Fetch moneyflow for one stock. Returns list of row tuples (no DB write)."""
    bare = _strip_suffix(stock_code)
    market = _market(stock_code)

    try:
        df = ak.stock_individual_fund_flow(stock=bare, market=market)
    except Exception as e:
        logger.warning(f"[{stock_code}] AKShare fetch failed: {e}")
        return []

    if df is None or df.empty:
        return []

    df.columns = [str(c).strip() for c in df.columns]

    col_map = {
        "日期": "trade_date",
        "超大单净流入-净额": "elg_net",
        "大单净流入-净额":   "lg_net",
        "中单净流入-净额":   "md_net",
        "小单净流入-净额":   "sm_net",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    if "trade_date" not in df.columns:
        logger.warning(f"[{stock_code}] Unexpected columns: {list(df.columns)}")
        return []

    df["trade_date"] = df["trade_date"].astype(str)
    df = df[df["trade_date"] >= start_date].copy()
    if df.empty:
        return []

    rows = []
    for _, row in df.iterrows():
        def _wan(col):
            try:
                v = row.get(col, 0)
                return float(v) * 1e4 if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        net_mf_amount = _wan("elg_net") + _wan("lg_net")

        rows.append((
            stock_code,
            row["trade_date"],
            0.0, 0.0, 0.0, 0.0,   # buy_sm/md/lg/elg vol (not available from this API)
            0.0, 0.0, 0.0, 0.0,   # sell_sm/md/lg/elg vol
            0.0,                   # net_mf_vol
            net_mf_amount,
        ))

    return rows


def write_rows(rows: list[tuple], envs: list[str]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO trade_stock_moneyflow
            (stock_code, trade_date,
             buy_sm_vol, buy_md_vol, buy_lg_vol, buy_elg_vol,
             sell_sm_vol, sell_md_vol, sell_lg_vol, sell_elg_vol,
             net_mf_vol, net_mf_amount)
        VALUES (%s,%s, %s,%s,%s,%s, %s,%s,%s,%s, %s,%s)
        ON DUPLICATE KEY UPDATE
            net_mf_amount = VALUES(net_mf_amount)
    """
    inserted = 0
    for env in envs:
        try:
            execute_many(sql, rows, env=env)
            inserted = len(rows)
        except Exception as e:
            logger.error(f"[env={env}] DB insert failed: {e}")
    return inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch trade_stock_moneyflow from AKShare")
    parser.add_argument("--stock", help="Single stock code")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--incremental", action="store_true",
                        help="Auto-detect start from last loaded date (yesterday if up to date)")
    parser.add_argument("--envs", default=os.getenv("DB_ENV", "online"),
                        help="Comma-separated DB envs to write to (e.g. local,online)")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--no-proxy", dest="no_proxy", action="store_true",
                        help="Clear proxy env vars before requests")
    args = parser.parse_args()

    envs = [e.strip() for e in args.envs.split(",") if e.strip()]
    # Use first env as source of truth for stock list and latest dates
    primary_env = envs[0]

    logger.info(f"envs={envs}, start={args.start}, workers={args.workers}")

    if args.incremental:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        args.start = yesterday

    if args.stock:
        bare = args.stock.split(".")[0]
        suffix = ".SH" if bare.startswith("6") else ".SZ"
        stocks = [{"stock_code": bare + suffix}]
    else:
        stocks = get_stock_list(primary_env)
        logger.info(f"Total stocks: {len(stocks)}")

    latest_dates = get_latest_dates(primary_env)
    logger.info(f"Already loaded stocks: {len(latest_dates)}")

    tasks = []
    for s in stocks:
        code = s["stock_code"]
        if code in latest_dates:
            last = datetime.strptime(latest_dates[code], "%Y-%m-%d")
            effective = (last + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            effective = args.start
        if effective <= datetime.now().strftime("%Y-%m-%d"):
            tasks.append((code, effective))

    logger.info(f"Stocks to update: {len(tasks)}")

    total_rows = 0
    errors = 0

    def _worker(task):
        code, start = task
        rows = fetch_one(code, start)
        n = write_rows(rows, envs)
        time.sleep(REQUEST_DELAY)
        return code, n

    if args.workers == 1 or len(tasks) <= 1:
        for i, task in enumerate(tasks):
            _, n = _worker(task)
            total_rows += n
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(tasks)}, inserted={total_rows}")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_worker, t): t for t in tasks}
            done = 0
            for fut in as_completed(futures):
                done += 1
                try:
                    _, n = fut.result()
                    total_rows += n
                    if done % 50 == 0:
                        logger.info(f"Progress: {done}/{len(tasks)}, inserted={total_rows}")
                except Exception as e:
                    errors += 1
                    logger.warning(f"Worker error: {e}")

    logger.info(f"Done. Total rows inserted: {total_rows}, errors: {errors}")


if __name__ == "__main__":
    main()
