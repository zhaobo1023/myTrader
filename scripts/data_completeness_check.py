#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/data_completeness_check.py

数据完整性检查工具 v1.0

检查五截面分析所需的各类数据的完备性，支持双环境切换。

用法：
    # 检查线上库
    DB_ENV=online python scripts/data_completeness_check.py

    # 检查本地库
    DB_ENV=local python scripts/data_completeness_check.py

    # 检查指定股票列表
    DB_ENV=online python scripts/data_completeness_check.py --stocks 000807 600938 000933

    # 只检查指定模块
    DB_ENV=online python scripts/data_completeness_check.py --modules financial industry moneyflow

    # 输出详细报告
    DB_ENV=online python scripts/data_completeness_check.py --verbose

    # 对比两套环境
    python scripts/data_completeness_check.py --compare
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from datetime import timedelta
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import execute_query


# ---------------------------------------------------------------------------
# 颜色/标记输出（纯文本，无 emoji）
# ---------------------------------------------------------------------------

def _ok(msg: str) -> str:
    return f"[OK]    {msg}"

def _warn(msg: str) -> str:
    return f"[WARN]  {msg}"

def _fail(msg: str) -> str:
    return f"[FAIL]  {msg}"

def _info(msg: str) -> str:
    return f"[INFO]  {msg}"

def _section(title: str) -> str:
    line = "-" * 60
    return f"\n{line}\n  {title}\n{line}"


# ---------------------------------------------------------------------------
# 单项检查
# ---------------------------------------------------------------------------

class CheckResult:
    def __init__(self, name: str, status: str, detail: str, fix_hint: str = ""):
        self.name = name
        self.status = status      # OK / WARN / FAIL
        self.detail = detail
        self.fix_hint = fix_hint

    def __str__(self) -> str:
        fn = {"OK": _ok, "WARN": _warn, "FAIL": _fail}.get(self.status, _info)
        s = fn(f"{self.name}: {self.detail}")
        if self.fix_hint and self.status != "OK":
            s += f"\n          -> 修复: {self.fix_hint}"
        return s


def _q(sql: str, params=None, env: str = "online") -> list:
    try:
        return execute_query(sql, params or [], env=env)
    except Exception as e:
        return [{"__error__": str(e)}]


def _latest_date(table: str, date_col: str, env: str) -> Optional[str]:
    rows = _q(f"SELECT MAX({date_col}) AS d FROM {table}", env=env)
    if rows and "__error__" not in rows[0]:
        return str(rows[0]["d"]) if rows[0]["d"] else None
    return None


def _count(table: str, where: str = "", env: str = "online") -> int:
    sql = f"SELECT COUNT(*) AS cnt FROM {table}"
    if where:
        sql += f" WHERE {where}"
    rows = _q(sql, env=env)
    if rows and "__error__" not in rows[0]:
        return int(rows[0]["cnt"])
    return -1


# ---------------------------------------------------------------------------
# 各模块检查函数
# ---------------------------------------------------------------------------

def check_trade_calendar(env: str) -> list[CheckResult]:
    results = []
    latest = _latest_date("trade_calendar", "cal_date", env)
    today = datetime.now().strftime("%Y-%m-%d")
    if latest and latest >= today:
        results.append(CheckResult("交易日历", "OK", f"最新日期 {latest}"))
    elif latest:
        results.append(CheckResult(
            "交易日历", "WARN", f"最新日期 {latest}，距今可能有缺口",
            "运行 python data_analyst/fetchers/akshare_fetcher.py --calendar"
        ))
    else:
        results.append(CheckResult(
            "交易日历", "FAIL", "表为空或不可访问",
            "运行 python data_analyst/fetchers/akshare_fetcher.py --calendar"
        ))
    return results


def check_stock_daily(env: str, stocks: list[str]) -> list[CheckResult]:
    results = []
    latest = _latest_date("trade_stock_daily", "trade_date", env)
    today_dt = datetime.now()
    # 最近 3 个自然日内有数据视为正常（考虑周末）
    threshold = (today_dt - timedelta(days=3)).strftime("%Y-%m-%d")

    if not latest:
        results.append(CheckResult(
            "日线行情", "FAIL", "trade_stock_daily 无数据",
            "DB_ENV=online python data_analyst/fetchers/akshare_fetcher.py"
        ))
        return results

    if latest < threshold:
        results.append(CheckResult(
            "日线行情", "WARN",
            f"最新日期 {latest}，可能未更新（超过 3 个自然日）",
            "DB_ENV=online python data_analyst/fetchers/akshare_fetcher.py"
        ))
    else:
        results.append(CheckResult("日线行情", "OK", f"最新日期 {latest}"))

    # 检查指定股票是否有数据
    if stocks:
        for code in stocks:
            fmt = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
            r = _q(
                "SELECT MAX(trade_date) AS d, COUNT(*) AS cnt FROM trade_stock_daily WHERE stock_code = %s",
                [fmt], env=env
            )
            if r and "__error__" not in r[0] and r[0]["cnt"] and r[0]["cnt"] > 0:
                results.append(CheckResult(
                    f"日线行情[{code}]", "OK",
                    f"共 {r[0]['cnt']} 条, 最新 {r[0]['d']}"
                ))
            else:
                results.append(CheckResult(
                    f"日线行情[{code}]", "FAIL", "无数据",
                    f"DB_ENV=online python data_analyst/fetchers/akshare_fetcher.py --stock {code}"
                ))
    return results


def check_financial(env: str, stocks: list[str]) -> list[CheckResult]:
    results = []
    # 全局：看最新年报覆盖只数
    rows = _q("""
        SELECT LEFT(report_date,4) AS yr, COUNT(DISTINCT stock_code) AS cnt
        FROM trade_stock_financial
        WHERE report_date LIKE '%%-12-31'
        GROUP BY yr
        ORDER BY yr DESC
        LIMIT 5
    """, env=env)

    if not rows or "__error__" in rows[0]:
        results.append(CheckResult(
            "财务数据", "FAIL", "trade_stock_financial 不可访问或为空",
            "python data_analyst/financial_fetcher/run_fetch.py"
        ))
        return results

    summary_lines = []
    latest_year = None
    for r in rows:
        summary_lines.append(f"{r['yr']}年: {r['cnt']} 只")
        if latest_year is None:
            latest_year = r["yr"]

    current_year = str(datetime.now().year - 1)  # 上一自然年的年报应该已发布
    if latest_year and latest_year >= current_year:
        results.append(CheckResult(
            "财务数据(全量)", "OK",
            " | ".join(summary_lines[:3])
        ))
    else:
        results.append(CheckResult(
            "财务数据(全量)", "WARN",
            f"最新年报 {latest_year} 年，{current_year} 年报可能未拉取 | " + " | ".join(summary_lines[:3]),
            "python data_analyst/financial_fetcher/run_fetch.py --year 2025"
        ))

    # 检查指定股票
    if stocks:
        for code in stocks:
            fmt = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
            r = _q("""
                SELECT report_date, roe
                FROM trade_stock_financial
                WHERE stock_code = %s AND report_date LIKE '%%-12-31'
                ORDER BY report_date DESC
                LIMIT 1
            """, [fmt], env=env)

            if r and "__error__" not in r[0] and r[0].get("report_date"):
                latest_rpt = str(r[0]["report_date"])
                rpt_year = int(latest_rpt[:4])
                months_old = (datetime.now().year - rpt_year) * 12 + datetime.now().month
                status = "OK" if months_old <= 18 else "WARN"
                hint = "" if status == "OK" else f"python data_analyst/financial_fetcher/run_fetch.py --stock {code}"
                results.append(CheckResult(
                    f"财务数据[{code}]", status,
                    f"最新年报 {latest_rpt}，距今 {months_old} 个月",
                    hint
                ))
            else:
                results.append(CheckResult(
                    f"财务数据[{code}]", "FAIL", "无数据",
                    f"python data_analyst/financial_fetcher/run_fetch.py --stock {code}"
                ))
    return results


def check_moneyflow(env: str, stocks: list[str]) -> list[CheckResult]:
    results = []
    cnt = _count("trade_stock_moneyflow", env=env)

    if cnt == 0:
        results.append(CheckResult(
            "主力资金流向", "FAIL",
            "trade_stock_moneyflow 表为空（0 行）",
            "见补充方案: scripts/fetch_moneyflow.py --all 或接入东方财富 API"
        ))
        return results

    latest = _latest_date("trade_stock_moneyflow", "trade_date", env)
    threshold = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    status = "OK" if latest and latest >= threshold else "WARN"
    hint = "" if status == "OK" else "scripts/fetch_moneyflow.py --incremental"
    results.append(CheckResult(
        "主力资金流向", status,
        f"共 {cnt} 条，最新日期 {latest}",
        hint
    ))

    # 指定股票
    if stocks and cnt > 0:
        for code in stocks:
            fmt = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
            r = _q(
                "SELECT COUNT(*) AS cnt, MAX(trade_date) AS d FROM trade_stock_moneyflow WHERE stock_code = %s",
                [fmt], env=env
            )
            if r and "__error__" not in r[0] and r[0]["cnt"] and int(r[0]["cnt"]) > 0:
                results.append(CheckResult(
                    f"资金流向[{code}]", "OK",
                    f"共 {r[0]['cnt']} 条，最新 {r[0]['d']}"
                ))
            else:
                results.append(CheckResult(
                    f"资金流向[{code}]", "FAIL", "无数据",
                    f"scripts/fetch_moneyflow.py --stock {code}"
                ))
    return results


def check_industry(env: str, stocks: list[str]) -> list[CheckResult]:
    results = []

    # 检查 trade_stock_industry 表
    cnt = _count("trade_stock_industry", env=env)
    if cnt == 0:
        results.append(CheckResult(
            "申万行业分类(trade_stock_industry)", "FAIL",
            "表为空，行业类型识别不可用",
            "scripts/fetch_industry.py"
        ))
    else:
        results.append(CheckResult(
            "申万行业分类", "OK", f"共 {cnt} 条"
        ))

    # 回退检查 trade_stock_basic.industry
    rows = _q(
        "SELECT COUNT(*) AS cnt FROM trade_stock_basic WHERE industry IS NOT NULL AND industry != ''",
        env=env
    )
    filled = int(rows[0]["cnt"]) if rows and "__error__" not in rows[0] else 0
    total = _count("trade_stock_basic", env=env)
    if filled > 0:
        results.append(CheckResult(
            "行业(trade_stock_basic.industry)", "OK",
            f"{filled}/{total} 只股票有行业字段（作为回退数据源）"
        ))
    else:
        results.append(CheckResult(
            "行业(trade_stock_basic.industry)", "WARN",
            f"industry 字段为空，行业分类将全部归为 UNKNOWN",
            "scripts/fetch_industry.py --basic"
        ))

    # 指定股票
    if stocks:
        for code in stocks:
            fmt = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
            r = _q(
                "SELECT industry FROM trade_stock_basic WHERE stock_code = %s LIMIT 1",
                [fmt], env=env
            )
            industry = r[0].get("industry") if r and "__error__" not in r[0] else None
            if industry:
                results.append(CheckResult(f"行业[{code}]", "OK", industry))
            else:
                results.append(CheckResult(
                    f"行业[{code}]", "WARN", "industry 字段为空，将归为 UNKNOWN"
                ))
    return results


def check_valuation(env: str) -> list[CheckResult]:
    results = []
    latest = _latest_date("trade_stock_daily_basic", "trade_date", env)
    threshold = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    if not latest:
        results.append(CheckResult(
            "估值数据(PE/PB)", "FAIL", "trade_stock_daily_basic 无数据",
            "DB_ENV=online python data_analyst/fetchers/akshare_fetcher.py --basic"
        ))
    elif latest < threshold:
        results.append(CheckResult(
            "估值数据(PE/PB)", "WARN",
            f"最新日期 {latest}，可能未及时更新",
            "DB_ENV=online python data_analyst/fetchers/akshare_fetcher.py --basic"
        ))
    else:
        results.append(CheckResult("估值数据(PE/PB)", "OK", f"最新日期 {latest}"))
    return results


def check_rps(env: str) -> list[CheckResult]:
    results = []
    for table in ["trade_stock_rps", "trade_rps_daily"]:
        cnt = _count(table, env=env)
        if cnt > 0:
            latest = _latest_date(table, "trade_date", env)
            threshold = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
            status = "OK" if latest and latest >= threshold else "WARN"
            hint = "" if status == "OK" else f"DB_ENV=online python -m strategist.doctor_tao.indicators"
            results.append(CheckResult(
                f"RPS数据({table})", status,
                f"共 {cnt} 条，最新 {latest}",
                hint
            ))
            return results  # 找到一个有数据的表就够了

    results.append(CheckResult(
        "RPS数据", "FAIL", "trade_stock_rps / trade_rps_daily 均无数据",
        "DB_ENV=online python -m strategist.doctor_tao.indicators"
    ))
    return results


def check_margin_north(env: str) -> list[CheckResult]:
    """检查融资融券和北向资金（情绪面另类数据）。"""
    results = []

    # 融资融券
    cnt = _count("trade_margin_trade", env=env)
    if cnt == 0:
        results.append(CheckResult(
            "融资融券余额", "FAIL",
            "trade_margin_trade 表为空，情绪面融资动量无法计算",
            "scripts/fetch_margin.py"
        ))
    else:
        latest = _latest_date("trade_margin_trade", "trade_date", env)
        results.append(CheckResult("融资融券余额", "OK", f"共 {cnt} 条，最新 {latest}"))

    # 北向持仓
    cnt = _count("trade_north_holding", env=env)
    if cnt == 0:
        results.append(CheckResult(
            "北向资金持仓", "FAIL",
            "trade_north_holding 表为空，北向偏离度无法计算",
            "scripts/fetch_north_holding.py"
        ))
    else:
        latest = _latest_date("trade_north_holding", "trade_date", env)
        results.append(CheckResult("北向资金持仓", "OK", f"共 {cnt} 条，最新 {latest}"))

    return results


# ---------------------------------------------------------------------------
# 汇总运行
# ---------------------------------------------------------------------------

MODULE_MAP = {
    "calendar":  ("交易日历",       lambda env, stocks: check_trade_calendar(env)),
    "daily":     ("日线行情",       lambda env, stocks: check_stock_daily(env, stocks)),
    "financial": ("财务数据",       lambda env, stocks: check_financial(env, stocks)),
    "moneyflow": ("主力资金流向",   lambda env, stocks: check_moneyflow(env, stocks)),
    "industry":  ("行业分类",       lambda env, stocks: check_industry(env, stocks)),
    "valuation": ("估值PE/PB",      lambda env, stocks: check_valuation(env)),
    "rps":       ("RPS强度",        lambda env, stocks: check_rps(env)),
    "margin":    ("融资/北向",      lambda env, stocks: check_margin_north(env)),
}


def run_check(env: str, stocks: list[str], modules: list[str], verbose: bool) -> dict:
    """执行检查，返回 {module: [CheckResult]}。"""
    active = modules if modules else list(MODULE_MAP.keys())
    all_results = {}

    for key in active:
        if key not in MODULE_MAP:
            print(f"[WARN] 未知模块: {key}，跳过")
            continue
        label, fn = MODULE_MAP[key]
        print(_section(f"{label}  [{key}]"))
        results = fn(env, stocks)
        for r in results:
            print(f"  {r}")
        all_results[key] = results

    return all_results


def print_summary(all_results: dict, env: str):
    ok_cnt = warn_cnt = fail_cnt = 0
    fail_items = []
    warn_items = []

    for module, results in all_results.items():
        for r in results:
            if r.status == "OK":
                ok_cnt += 1
            elif r.status == "WARN":
                warn_cnt += 1
                warn_items.append(r)
            else:
                fail_cnt += 1
                fail_items.append(r)

    total = ok_cnt + warn_cnt + fail_cnt
    print(_section(f"检查汇总  [环境: {env}]"))
    print(f"  总计: {total} 项  |  OK: {ok_cnt}  |  WARN: {warn_cnt}  |  FAIL: {fail_cnt}")

    if fail_items:
        print("\n  [FAIL] 需要立即修复:")
        for r in fail_items:
            print(f"    - {r.name}: {r.detail}")
            if r.fix_hint:
                print(f"      修复: {r.fix_hint}")

    if warn_items:
        print("\n  [WARN] 建议关注:")
        for r in warn_items:
            print(f"    - {r.name}: {r.detail}")
            if r.fix_hint:
                print(f"      修复: {r.fix_hint}")

    score = int(ok_cnt / total * 100) if total > 0 else 0
    print(f"\n  数据完整度得分: {score}%")
    return score


def run_compare(stocks: list[str], modules: list[str]):
    """对比 local 和 online 两套环境。"""
    print("\n" + "=" * 60)
    print("  双环境对比检查")
    print("=" * 60)

    for env in ["local", "online"]:
        print(f"\n{'='*20} 环境: {env} {'='*20}")
        all_results = run_check(env, stocks, modules, verbose=False)
        print_summary(all_results, env)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="数据完整性检查工具，支持 local/online 双环境"
    )
    parser.add_argument(
        "--stocks", nargs="+", default=[],
        metavar="CODE",
        help="指定检查的股票代码（6位，如 000807 600938）"
    )
    parser.add_argument(
        "--modules", nargs="+", default=[],
        choices=list(MODULE_MAP.keys()),
        metavar="MODULE",
        help=f"指定检查模块，可选: {', '.join(MODULE_MAP.keys())}（默认全部）"
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="同时检查 local 和 online 两套环境并对比"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="输出详细信息"
    )
    args = parser.parse_args()

    env = os.getenv("DB_ENV", "online")

    print(f"\n数据完整性检查  |  环境: {env}  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.stocks:
        print(f"检查股票: {', '.join(args.stocks)}")
    if args.modules:
        print(f"检查模块: {', '.join(args.modules)}")

    if args.compare:
        run_compare(args.stocks, args.modules)
    else:
        all_results = run_check(env, args.stocks, args.modules, args.verbose)
        score = print_summary(all_results, env)
        sys.exit(0 if score >= 60 else 1)


if __name__ == "__main__":
    main()
