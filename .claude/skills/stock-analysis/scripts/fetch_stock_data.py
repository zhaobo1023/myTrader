#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch all data needed for a stock analysis report from the ECS MySQL database.

The model should not hand-write these queries: column names differ between tables
(stock_code, not ts_code), money units differ per table (yuan / yi / wan), and the
financial_* tables store bare 6-digit codes while trade_* tables store suffixed
ones. Getting any of those wrong returns silently-empty results rather than an error.

Usage:
    fetch_stock_data.py --resolve "长电科技"
    fetch_stock_data.py --code 600584.SH [--json]
    fetch_stock_data.py --code 600584.SH --peers
    fetch_stock_data.py --codes 600584.SH,688981.SH --overview

Requires: ssh alias `aliyun-ecs` reachable, and ONLINE_DB_PASSWORD in the repo .env
(same source config/settings.py reads; no extra setup needed).
Reports facts only (how many periods of each dataset exist); it does not decide
whether the data is sufficient to draw conclusions.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

SSH_HOST = "aliyun-ecs"
SSH_TIMEOUT = 120

# Repo root is four levels up: .claude/skills/stock-analysis/scripts/ -> repo/
_ENV_PATH = Path(__file__).resolve().parents[4] / ".env"

# Which .env prefix to read for user+password. These two must come from the same
# prefix -- mixing them (e.g. mytrader_user with ONLINE_DB_PASSWORD) yields
# "Access denied", because the accounts have different passwords.
DB_PREFIX = "STOCK_ANALYSIS"   # falls back to ONLINE_* if unset

# The analysis tables live in `trade`, NOT in the db named by ONLINE_DB_NAME
# (that one is `wucai_trade`, the migration *source*). Verified via --probe:
# trade.trade_stock_info has 5495 rows; wucai_trade has no such table.
# Override with STOCK_ANALYSIS_DB_NAME in .env if this ever moves.
DEFAULT_DB_NAME = "trade"

# Unit conversion to 亿元. Verified against live data: total_mv/circ_mv and the
# financial_* tables are ALREADY in 亿元 (the DDL comments claiming 万元 are
# wrong); only trade_stock_financial money columns are in 元.
YUAN_TO_YI = 1.0 / 1e8       # trade_stock_financial money columns are in 元


def die(msg, code=1):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def db_credentials():
    """Read user+password as one consistent set from .env; resolve the db name.

    user/password always come from the same prefix (they are one credential).
    The db name is resolved separately, because the analysis tables are in
    `trade` while ONLINE_DB_NAME points at the migration source `wucai_trade`.
    """
    env = dotenv_values(_ENV_PATH)
    for prefix in (DB_PREFIX, "ONLINE"):
        user = env.get(f"{prefix}_DB_USER")
        password = env.get(f"{prefix}_DB_PASSWORD")
        if user and password:
            name = (env.get(f"{DB_PREFIX}_DB_NAME")
                    or env.get("STOCK_ANALYSIS_DB_NAME")
                    or DEFAULT_DB_NAME)
            return user, password, name, prefix
    die(
        f"未能从 {_ENV_PATH} 读到数据库用户名与密码。\n"
        f"需要同一前缀下的两项（必须同源，混用会 Access denied）：\n"
        f"  {DB_PREFIX}_DB_USER / {DB_PREFIX}_DB_PASSWORD\n"
        f"（或退回 ONLINE_DB_USER / ONLINE_DB_PASSWORD）\n"
        f"库名默认 {DEFAULT_DB_NAME}，可用 {DB_PREFIX}_DB_NAME 覆盖。"
    )


def run_sql(sql):
    """Run one SQL statement over SSH, return list of dicts.

    mysql -B gives tab-separated output with a header row. NULL comes back as
    the literal string "NULL", which we map to None.
    """
    db_user, password, db_name, _ = db_credentials()

    # Single-quote the SQL for the remote shell; escape any embedded single quotes.
    remote_sql = sql.replace("'", "'\"'\"'")
    # MYSQL_PWD keeps the password out of the remote process list and out of
    # mysql's "using a password on the command line is insecure" warning.
    remote_cmd = (
        f"MYSQL_PWD='{password}' mysql -u {db_user} {db_name} -B -e '{remote_sql}'"
    )
    try:
        proc = subprocess.run(
            ["ssh", SSH_HOST, remote_cmd],
            capture_output=True, text=True, timeout=SSH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        die(f"SSH 查询超时（{SSH_TIMEOUT}s）。检查 {SSH_HOST} 是否可达。")

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        # Never echo the password back out, even on failure.
        stderr = stderr.replace(password, "***")
        die(f"MySQL 查询失败：{stderr}")

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        vals = ln.split("\t")
        row = {}
        for k, v in zip(header, vals):
            row[k] = None if v == "NULL" else v
        rows.append(row)
    return rows


def probe():
    """Report which databases/tables the configured credentials can actually see.

    Exists because the credential set and the database holding the analysis
    tables were mismatched once already (quant_user/wucai_trade vs
    mytrader_user/trade). Run this before guessing at config.
    """
    user, _, db_name, prefix = db_credentials()
    print(f"凭据来源：.env 的 {prefix}_DB_*  ->  user={user}  db={db_name}\n")

    dbs = run_sql("SHOW DATABASES")
    key = list(dbs[0].keys())[0] if dbs else None
    names = [r[key] for r in dbs] if key else []
    print(f"该账号可见的库（{len(names)}）：{', '.join(names)}\n")

    probe_table = "trade_stock_info"
    for d in names:
        if d in ("information_schema", "performance_schema", "mysql", "sys"):
            continue
        rows = run_sql(
            "SELECT COUNT(*) AS n FROM information_schema.tables "
            f"WHERE table_schema = '{esc(d)}' AND table_name = '{probe_table}'"
        )
        has = rows and rows[0].get("n") not in (None, "0", 0)
        if has:
            cnt = run_sql(f"SELECT COUNT(*) AS n FROM `{d}`.{probe_table}")
            n = cnt[0]["n"] if cnt else "?"
            print(f"  [FOUND] {d}.{probe_table}  共 {n} 行  <-- 分析数据在这个库")
        else:
            print(f"  [  --  ] {d} 无 {probe_table}")

    print("\n若 FOUND 的库名与上面的 db= 不一致，在 .env 中加一套同源凭据：")
    print(f"  {DB_PREFIX}_DB_USER / {DB_PREFIX}_DB_PASSWORD / {DB_PREFIX}_DB_NAME")


def to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def convert(row, fields, factor):
    """Scale the given numeric fields by factor, in place."""
    for f in fields:
        val = to_float(row.get(f))
        row[f] = round(val * factor, 4) if val is not None else None
    return row


def bare_code(code):
    """600584.SH -> 600584 (financial_* tables store codes without the suffix)."""
    return code.split(".")[0]


def esc(s):
    """Escape a value for inclusion in a SQL string literal."""
    return str(s).replace("\\", "\\\\").replace("'", "''")


def fetch_with_code_fallback(sql_template, code):
    """Query with the suffixed code; if it returns 0 rows, retry bare 6-digit.

    Real gotcha: research_announcements and the financial_* tables may store
    either form. A suffixed-only query returns 0 rows silently, which reads as
    "this company has no filings" rather than "wrong code format".
    """
    rows = run_sql(sql_template.format(code=esc(code)))
    if not rows:
        rows = run_sql(sql_template.format(code=esc(bare_code(code))))
    return rows


def resolve(query):
    """Look up a stock by name or code. Prints matches; exits 2 if none."""
    q = esc(query)
    sql = (
        "SELECT stock_code, stock_name, industry, listed_date, main_business "
        "FROM trade_stock_info "
        f"WHERE stock_code LIKE '{q}%' OR stock_name = '{q}' OR stock_name LIKE '%{q}%' "
        "ORDER BY CASE WHEN stock_name = '" + q + "' THEN 0 ELSE 1 END, stock_code "
        "LIMIT 10"
    )
    rows = run_sql(sql)
    if not rows:
        print(f"[NOT_FOUND] 未找到匹配「{query}」的股票。", file=sys.stderr)
        sys.exit(2)
    for r in rows:
        biz = (r.get("main_business") or "")[:60]
        print(f"{r['stock_code']}\t{r['stock_name']}\t{r.get('industry') or '-'}\t{biz}")
    return rows


def fetch_all(code):
    """Fetch the nine datasets for one stock. All money normalised to 亿元."""
    c = esc(code)
    data = {}

    data["info"] = run_sql(
        "SELECT stock_code, stock_name, industry, province, listed_date, main_business "
        f"FROM trade_stock_info WHERE stock_code = '{c}' LIMIT 1"
    )

    # Column names verified against the live `trade` schema, which differs from
    # the DDL in config/models.py (net_margin not net_profit_margin, etc).
    # This table DOES carry revenue/net_profit, in 元 -> convert to 亿元.
    fin = run_sql(
        "SELECT report_date, revenue, net_profit, eps, roe, roa, gross_margin, "
        "net_margin, debt_ratio, current_ratio, operating_cashflow, "
        "total_assets, total_equity, data_source "
        f"FROM trade_stock_financial WHERE stock_code = '{c}' "
        "ORDER BY report_date DESC LIMIT 12"
    )
    data["financial_summary"] = [
        convert(r, ["revenue", "net_profit", "operating_cashflow",
                    "total_assets", "total_equity"], YUAN_TO_YI)
        for r in fin
    ]

    # financial_* tables are already in 亿元.
    data["income"] = fetch_with_code_fallback(
        "SELECT report_date, report_type, revenue, net_profit, net_profit_yoy, "
        "roe, gross_margin, eps FROM financial_income "
        "WHERE stock_code = '{code}' ORDER BY report_date DESC LIMIT 12", code)

    data["balance"] = fetch_with_code_fallback(
        "SELECT report_date, total_assets, total_equity "
        "FROM financial_balance WHERE stock_code = '{code}' "
        "ORDER BY report_date DESC LIMIT 8", code)

    data["cashflow"] = fetch_with_code_fallback(
        "SELECT report_date, operating_cashflow, investing_cashflow, "
        "financing_cashflow, net_cashflow FROM financial_cashflow "
        "WHERE stock_code = '{code}' ORDER BY report_date DESC LIMIT 8", code)

    # total_mv/circ_mv are 万元 -> 亿元.
    valuation = run_sql(
        "SELECT trade_date, total_mv, circ_mv, pe_ttm, pb, ps_ttm, "
        "total_share, circ_share, turnover_rate "
        f"FROM trade_stock_daily_basic WHERE stock_code = '{c}' "
        "ORDER BY trade_date DESC LIMIT 5"
    )
    # total_mv/circ_mv are already in 亿元 in the live table -- no conversion.
    data["valuation"] = valuation

    data["daily"] = run_sql(
        "SELECT trade_date, open_price, high_price, low_price, close_price, "
        "volume, amount, turnover_rate "
        f"FROM trade_stock_daily WHERE stock_code = '{c}' "
        "ORDER BY trade_date DESC LIMIT 20"
    )

    data["factors"] = run_sql(
        "SELECT calc_date, mom_20, mom_60, reversal_5, turnover, vol_ratio, "
        "volatility_20, close "
        f"FROM trade_stock_basic_factor WHERE stock_code = '{c}' "
        "ORDER BY calc_date DESC LIMIT 5"
    )

    data["technical"] = run_sql(
        "SELECT trade_date, ma5, ma10, ma20, ma60, macd_dif, macd_dea, "
        "macd_histogram, rsi_6, rsi_12, rsi_24, kdj_k, kdj_d, kdj_j "
        f"FROM trade_technical_indicator WHERE stock_code = '{c}' "
        "ORDER BY trade_date DESC LIMIT 5"
    )

    # research_announcements keys on `code`, NOT `stock_code`, and stores the
    # bare 6-digit form -- so the suffixed query returns 0 rows silently.
    data["announcements"] = fetch_with_code_fallback(
        "SELECT ann_date, ann_type, title, direction, magnitude, summary "
        "FROM research_announcements WHERE code = '{code}' "
        "ORDER BY ann_date DESC LIMIT 10", code)

    data["news"] = fetch_with_code_fallback(
        "SELECT title, source, publish_time, event_type, event_category, "
        "event_signal FROM stock_news WHERE stock_code = '{code}' "
        "ORDER BY publish_time DESC LIMIT 5", code)

    data["completeness"] = completeness(data)
    return data


def completeness(data):
    """State the facts about coverage. Deciding if it's *enough* is the model's job."""
    def annual(rows):
        return sum(1 for r in rows if str(r.get("report_date", ""))[5:7] == "12")

    return {
        "financial_periods": len(data["financial_summary"]),
        "income_periods": len(data["income"]),
        "income_annual_periods": annual(data["income"]),
        "balance_periods": len(data["balance"]),
        "cashflow_periods": len(data["cashflow"]),
        "cashflow_annual_periods": annual(data["cashflow"]),
        "valuation_days": len(data["valuation"]),
        "daily_days": len(data["daily"]),
        "factor_days": len(data["factors"]),
        "technical_days": len(data["technical"]),
        "announcements": len(data["announcements"]),
        "news": len(data["news"]),
        "has_current_pe": bool(data["valuation"] and data["valuation"][0].get("pe_ttm")),
        "has_current_pb": bool(data["valuation"] and data["valuation"][0].get("pb")),
    }


def fetch_peers(code, limit=5):
    """Same-industry peers by market cap, all on one shared trade_date.

    A shared base date matters: letting each stock use its own "latest" day
    skews comparison when some are suspended or lag in data.
    """
    c = esc(code)
    info = run_sql(
        f"SELECT stock_code, stock_name, industry FROM trade_stock_info "
        f"WHERE stock_code = '{c}' LIMIT 1"
    )
    if not info:
        die(f"找不到股票 {code}")
    industry = info[0].get("industry")
    if not industry:
        return {"industry": None, "base_date": None, "peers": [],
                "note": "该股票无行业分类，无法自动选取可比公司"}

    # Use the target stock's own latest valuation date as the base, so the
    # comparison is anchored to the company being analysed. The global
    # MAX(trade_date) would bias peer selection toward whichever stocks happen
    # to have the freshest data (only ~720 of 5495 have data on the newest day).
    own = run_sql(
        "SELECT MAX(trade_date) AS d FROM trade_stock_daily_basic "
        f"WHERE stock_code = '{c}' AND total_mv IS NOT NULL"
    )
    base_date = own[0]["d"] if own and own[0].get("d") else None
    if not base_date:
        die(f"{code} 无估值数据，无法确定基准交易日")

    ind = esc(industry)
    peers = run_sql(
        "SELECT i.stock_code, i.stock_name, b.total_mv, b.pe_ttm, b.pb, b.ps_ttm "
        "FROM trade_stock_info i "
        "JOIN trade_stock_daily_basic b ON b.stock_code = i.stock_code "
        f"WHERE i.industry = '{ind}' AND i.stock_code != '{c}' "
        f"AND b.trade_date = '{esc(base_date)}' AND b.total_mv IS NOT NULL "
        f"ORDER BY b.total_mv DESC LIMIT {int(limit)}"
    )

    for p in peers:
        fin = run_sql(
            "SELECT report_date, roe, gross_margin, net_margin, revenue, net_profit "
            f"FROM trade_stock_financial WHERE stock_code = '{esc(p['stock_code'])}' "
            "ORDER BY report_date DESC LIMIT 1"
        )
        p["financial"] = (convert(fin[0], ["revenue", "net_profit"], YUAN_TO_YI)
                          if fin else None)
        inc = fetch_with_code_fallback(
            "SELECT report_date, revenue, net_profit FROM financial_income "
            "WHERE stock_code = '{code}' ORDER BY report_date DESC LIMIT 1",
            p["stock_code"])
        p["income"] = inc[0] if inc else None

    return {"industry": industry, "base_date": base_date, "peers": peers}


def shared_base_date(quoted_codes, n_codes):
    """Latest trade_date on which *every* requested stock has valuation data.

    The global MAX(trade_date) does not work: coverage is uneven (only ~720 of
    5495 stocks have data on the most recent day), so pinning the global max
    silently yields NULL market caps for most stocks. Per-stock "latest" would
    fix the NULLs but breaks comparability, which is the whole point of a shared
    base date. So: newest date where the full set is present.
    """
    rows = run_sql(
        "SELECT trade_date FROM trade_stock_daily_basic "
        f"WHERE stock_code IN ({quoted_codes}) AND total_mv IS NOT NULL "
        f"GROUP BY trade_date HAVING COUNT(DISTINCT stock_code) = {int(n_codes)} "
        "ORDER BY trade_date DESC LIMIT 1"
    )
    return rows[0]["trade_date"] if rows else None


def fetch_overview(codes):
    """Lightweight batch pull for the sector overview comparison table."""
    quoted = ",".join(f"'{esc(c)}'" for c in codes)

    # Only count codes that actually exist, or one bad code would make a
    # complete-coverage date impossible and drop everyone to NULL.
    known = run_sql(
        f"SELECT stock_code FROM trade_stock_info WHERE stock_code IN ({quoted})"
    )
    known_codes = [r["stock_code"] for r in known]
    base_date = None
    if known_codes:
        kq = ",".join(f"'{esc(c)}'" for c in known_codes)
        base_date = shared_base_date(kq, len(known_codes))
    if not base_date:
        base = run_sql("SELECT MAX(trade_date) AS d FROM trade_stock_daily_basic")
        base_date = base[0]["d"] if base else None

    rows = run_sql(
        "SELECT i.stock_code, i.stock_name, i.industry, b.total_mv, b.pe_ttm, "
        "b.pb, b.ps_ttm, b.turnover_rate "
        "FROM trade_stock_info i "
        "LEFT JOIN trade_stock_daily_basic b ON b.stock_code = i.stock_code "
        f"AND b.trade_date = '{esc(base_date)}' "
        f"WHERE i.stock_code IN ({quoted})"
    )

    for r in rows:
        fin = run_sql(
            "SELECT report_date, roe, gross_margin, net_margin, revenue, net_profit "
            f"FROM trade_stock_financial WHERE stock_code = '{esc(r['stock_code'])}' "
            "ORDER BY report_date DESC LIMIT 1"
        )
        r["financial"] = (convert(fin[0], ["revenue", "net_profit"], YUAN_TO_YI)
                          if fin else None)
        inc = fetch_with_code_fallback(
            "SELECT report_date, revenue, net_profit, net_profit_yoy "
            "FROM financial_income WHERE stock_code = '{code}' "
            "ORDER BY report_date DESC LIMIT 1", r["stock_code"])
        r["income"] = inc[0] if inc else None
        fac = run_sql(
            "SELECT calc_date, mom_20, mom_60, turnover, volatility_20 "
            f"FROM trade_stock_basic_factor WHERE stock_code = '{esc(r['stock_code'])}' "
            "ORDER BY calc_date DESC LIMIT 1"
        )
        r["factors"] = fac[0] if fac else None

    found = {r["stock_code"] for r in rows}
    return {
        "base_date": base_date,
        "stocks": rows,
        "not_found": [c for c in codes if c not in found],
    }


def print_summary(data):
    """Human-readable digest, for when --json isn't needed."""
    info = data["info"][0] if data["info"] else {}
    print(f"股票：{info.get('stock_name', '?')}（{info.get('stock_code', '?')}）"
          f"  行业：{info.get('industry') or '-'}")
    if data["valuation"]:
        v = data["valuation"][0]
        print(f"最新（{v['trade_date']}）：市值 {v['total_mv']} 亿元  "
              f"PE(TTM) {v['pe_ttm']}  PB {v['pb']}  PS(TTM) {v['ps_ttm']}")
    print("\n数据完备性（事实陈述，是否足够由模型判断）：")
    for k, v in data["completeness"].items():
        print(f"  {k}: {v}")
    print("\n完整数据请加 --json")


def main():
    ap = argparse.ArgumentParser(description="拉取 A 股分析所需的全部数据")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--resolve", metavar="NAME_OR_CODE", help="按名称/代码查股票")
    g.add_argument("--code", metavar="CODE", help="单只股票代码，如 600584.SH")
    g.add_argument("--codes", metavar="C1,C2", help="多只代码，逗号分隔（配合 --overview）")
    g.add_argument("--probe", action="store_true", help="诊断：看当前凭据能访问哪些库/表")
    ap.add_argument("--peers", action="store_true", help="只拉可比公司")
    ap.add_argument("--overview", action="store_true", help="批量轻量数据（题材总览用）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if args.probe:
        probe()
        return

    if args.resolve:
        resolve(args.resolve)
        return

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        if not codes:
            die("--codes 为空")
        out = fetch_overview(codes)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return

    if args.peers:
        out = fetch_peers(args.code)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return

    data = fetch_all(args.code)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print_summary(data)


if __name__ == "__main__":
    main()
