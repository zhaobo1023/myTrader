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

DB_USER = "mytrader_user"
DB_NAME = "trade"
SSH_HOST = "aliyun-ecs"
SSH_TIMEOUT = 120

# Repo root is four levels up: .claude/skills/stock-analysis/scripts/ -> repo/
_ENV_PATH = Path(__file__).resolve().parents[4] / ".env"

# Unit conversion to 亿元. Tables not listed here are already in 亿元.
WAN_TO_YI = 1.0 / 10000      # total_mv/circ_mv are in 万元
YUAN_TO_YI = 1.0 / 1e8       # trade_stock_financial money columns are in 元


def die(msg, code=1):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def run_sql(sql):
    """Run one SQL statement over SSH, return list of dicts.

    mysql -B gives tab-separated output with a header row. NULL comes back as
    the literal string "NULL", which we map to None.
    """
    password = dotenv_values(_ENV_PATH).get("ONLINE_DB_PASSWORD")
    if not password:
        die(f"未能从 {_ENV_PATH} 读到 ONLINE_DB_PASSWORD。"
            "确认在仓库根目录的 .env 中已配置（与 config/settings.py 同源）。")

    # Single-quote the SQL for the remote shell; escape any embedded single quotes.
    remote_sql = sql.replace("'", "'\"'\"'")
    remote_cmd = (
        f"mysql -u {DB_USER} -p'{password}' {DB_NAME} -B -e '{remote_sql}'"
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

    # Ratios only (no money columns) -> no conversion needed.
    data["financial_summary"] = run_sql(
        "SELECT report_date, roe, net_profit_margin, gross_profit_margin, "
        "debt_to_asset, current_ratio, quick_ratio, eps, bvps, cfps "
        f"FROM trade_stock_financial WHERE stock_code = '{c}' "
        "ORDER BY report_date DESC LIMIT 12"
    )

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
        "SELECT trade_date, total_mv, circ_mv, pe_ttm, pb, ps_ttm, dv_ttm, turnover_rate "
        f"FROM trade_stock_daily_basic WHERE stock_code = '{c}' "
        "ORDER BY trade_date DESC LIMIT 5"
    )
    data["valuation"] = [convert(r, ["total_mv", "circ_mv"], WAN_TO_YI) for r in valuation]

    data["daily"] = run_sql(
        "SELECT trade_date, open, high, low, close, vol, amount "
        f"FROM trade_stock_daily WHERE stock_code = '{c}' "
        "ORDER BY trade_date DESC LIMIT 20"
    )

    data["factors"] = run_sql(
        f"SELECT * FROM trade_stock_basic_factor WHERE stock_code = '{c}' "
        "ORDER BY calc_date DESC LIMIT 5"
    )

    data["technical"] = run_sql(
        f"SELECT * FROM trade_technical_indicator WHERE stock_code = '{c}' "
        "ORDER BY trade_date DESC LIMIT 5"
    )

    data["announcements"] = fetch_with_code_fallback(
        "SELECT * FROM research_announcements WHERE stock_code = '{code}' "
        "ORDER BY ann_date DESC LIMIT 10", code)

    data["news"] = fetch_with_code_fallback(
        "SELECT * FROM stock_news WHERE stock_code = '{code}' LIMIT 5", code)

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

    base = run_sql("SELECT MAX(trade_date) AS d FROM trade_stock_daily_basic")
    base_date = base[0]["d"] if base else None
    if not base_date:
        die("无法确定基准交易日")

    ind = esc(industry)
    peers = run_sql(
        "SELECT i.stock_code, i.stock_name, b.total_mv, b.pe_ttm, b.pb, b.ps_ttm "
        "FROM trade_stock_info i "
        "JOIN trade_stock_daily_basic b ON b.stock_code = i.stock_code "
        f"WHERE i.industry = '{ind}' AND i.stock_code != '{c}' "
        f"AND b.trade_date = '{esc(base_date)}' AND b.total_mv IS NOT NULL "
        f"ORDER BY b.total_mv DESC LIMIT {int(limit)}"
    )
    peers = [convert(p, ["total_mv"], WAN_TO_YI) for p in peers]

    for p in peers:
        fin = run_sql(
            "SELECT report_date, roe, gross_profit_margin, net_profit_margin "
            f"FROM trade_stock_financial WHERE stock_code = '{esc(p['stock_code'])}' "
            "ORDER BY report_date DESC LIMIT 1"
        )
        p["financial"] = fin[0] if fin else None
        inc = fetch_with_code_fallback(
            "SELECT report_date, revenue, net_profit FROM financial_income "
            "WHERE stock_code = '{code}' ORDER BY report_date DESC LIMIT 1",
            p["stock_code"])
        p["income"] = inc[0] if inc else None

    return {"industry": industry, "base_date": base_date, "peers": peers}


def fetch_overview(codes):
    """Lightweight batch pull for the sector overview comparison table."""
    quoted = ",".join(f"'{esc(c)}'" for c in codes)
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
    rows = [convert(r, ["total_mv"], WAN_TO_YI) for r in rows]

    for r in rows:
        fin = run_sql(
            "SELECT report_date, roe, gross_profit_margin, net_profit_margin "
            f"FROM trade_stock_financial WHERE stock_code = '{esc(r['stock_code'])}' "
            "ORDER BY report_date DESC LIMIT 1"
        )
        r["financial"] = fin[0] if fin else None
        inc = fetch_with_code_fallback(
            "SELECT report_date, revenue, net_profit, net_profit_yoy "
            "FROM financial_income WHERE stock_code = '{code}' "
            "ORDER BY report_date DESC LIMIT 1", r["stock_code"])
        r["income"] = inc[0] if inc else None
        fac = run_sql(
            f"SELECT * FROM trade_stock_basic_factor WHERE stock_code = '{esc(r['stock_code'])}' "
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
    ap.add_argument("--peers", action="store_true", help="只拉可比公司")
    ap.add_argument("--overview", action="store_true", help="批量轻量数据（题材总览用）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

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
