# -*- coding: utf-8 -*-
"""financial data fetcher via akshare

Adapted from example code, replaced sqlalchemy with config.db.
"""

import logging
import sys
import os
import time
from datetime import datetime
from typing import List
from typing import Dict

import akshare as ak
import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .storage import FinancialStorage
from .config import FinancialFetcherConfig

logger = logging.getLogger(__name__)


def safe_float(val, default=None):
    """safe float conversion, handle '--' and NaN"""
    try:
        if pd.isna(val) or str(val).strip() in ('--', '-', '', 'nan'):
            return default
        return float(str(val).replace('%', '').replace(',', ''))
    except Exception:
        return default


def _report_type(month: int) -> str:
    mapping = {3: "一季报", 6: "半年报", 9: "三季报", 12: "年报"}
    return mapping.get(month, "其他")


def _to_em_symbol(stock_code: str) -> str:
    """convert 6-digit code to east money format (e.g. 600015 -> sh600015, 920xxx -> bj920xxx)"""
    code = stock_code.strip()
    if code.startswith(("sh", "sz", "bj", "SH", "SZ", "BJ")):
        return code.lower()
    if code.startswith(("92", "8", "4")):
        prefix = "bj"
    elif code.startswith("6"):
        prefix = "sh"
    else:
        prefix = "sz"
    return prefix + code


def _to_secucode(stock_code: str) -> str:
    """convert 6-digit code to SECUCODE format (e.g. 600015 -> 600015.SH, 920xxx -> 920xxx.BJ)"""
    code = stock_code.strip()
    if "." in code:
        return code.upper()
    if code.startswith(("92", "8", "4")):
        suffix = "BJ"
    elif code.startswith("6"):
        suffix = "SH"
    else:
        suffix = "SZ"
    return f"{code}.{suffix}"


def fetch_income(stock_code: str, stock_name: str) -> List[dict]:
    """profit statement from akshare (east money)"""
    records = []
    em_code = _to_em_symbol(stock_code)
    try:
        df = ak.stock_profit_sheet_by_report_em(symbol=em_code)
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            raw = str(row.get("REPORT_DATE", ""))[:10]
            try:
                report_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except Exception:
                continue

            revenue_raw = safe_float(row.get("OPERATE_INCOME"))
            operate_cost_raw = safe_float(row.get("OPERATE_COST"))
            net_profit_raw = safe_float(row.get("PARENT_NETPROFIT"))

            # Compute gross margin: (revenue - cost) / revenue * 100
            gross_margin = None
            if revenue_raw and operate_cost_raw and revenue_raw > 0:
                gross_margin = round((revenue_raw - operate_cost_raw) / revenue_raw * 100, 2)

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_date": report_date,
                "report_type": _report_type(report_date.month),
                "revenue": round(revenue_raw / 1e8, 4) if revenue_raw else None,
                "net_profit": round(net_profit_raw / 1e8, 4) if net_profit_raw else None,
                "net_profit_yoy": safe_float(row.get("PARENT_NETPROFIT_YOY")),
                "eps": safe_float(row.get("BASIC_EPS")),
                "roe": None,
                "gross_margin": gross_margin,
            })
    except Exception as e:
        logger.error(f"[{stock_code}] income fetch failed: {e}")
    return records


def fetch_balance(stock_code: str, stock_name: str) -> List[dict]:
    """balance sheet from akshare"""
    records = []
    em_code = _to_em_symbol(stock_code)
    try:
        df = ak.stock_balance_sheet_by_report_em(symbol=em_code)
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            raw = str(row.get("REPORT_DATE", ""))[:10]
            try:
                report_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except Exception:
                continue

            total_assets_raw = safe_float(row.get("TOTAL_ASSETS"))
            total_equity_raw = safe_float(row.get("TOTAL_EQUITY"))

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_date": report_date,
                "total_assets": round(total_assets_raw / 1e8, 4) if total_assets_raw else None,
                "total_equity": round(total_equity_raw / 1e8, 4) if total_equity_raw else None,
                "loan_total": None,
                "npl_ratio": None,
                "provision_coverage": None,
                "provision_ratio": None,
                "cap_adequacy_ratio": None,
                "tier1_ratio": None,
                "nim": None,
            })
    except Exception as e:
        logger.error(f"[{stock_code}] balance fetch failed: {e}")
    return records


def fetch_bank_indicators(stock_code: str, stock_name: str) -> List[dict]:
    """bank-specific indicators: NPL, provision coverage, CAR, NIM

    Uses stock_financial_analysis_indicator_em which returns richer data
    including bank-specific fields (NONPERLOAN, BLDKBBL, etc.).
    Column mapping (akshare 1.18.x):
        NONPERLOAN          -> NPL ratio
        BLDKBBL             -> provision coverage
        LOAN_PROVISION_RATIO -> loan provision ratio
        NEWCAPITALADER      -> capital adequacy ratio
        FIRST_ADEQUACY_RATIO -> tier1 ratio
        NET_INTEREST_MARGIN -> NIM
        GROSSLOANS          -> loan total
        ROEJQ               -> ROE (weighted)
    """
    records = []
    secu_code = _to_secucode(stock_code)
    try:
        df = ak.stock_financial_analysis_indicator_em(
            symbol=secu_code, indicator="按报告期"
        )
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            raw = str(row.get("REPORT_DATE", ""))[:10]
            try:
                report_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except Exception:
                continue

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_date": report_date,
                "roe": safe_float(row.get("ROEJQ")),
                "npl_ratio": safe_float(row.get("NONPERLOAN")),
                "provision_coverage": safe_float(row.get("BLDKBBL")),
                "provision_ratio": safe_float(row.get("LOAN_PROVISION_RATIO")),
                "cap_adequacy_ratio": safe_float(row.get("NEWCAPITALADER")),
                "tier1_ratio": safe_float(row.get("FIRST_ADEQUACY_RATIO")),
                "nim": safe_float(row.get("NET_INTEREST_MARGIN")),
                "loan_total": round(
                    safe_float(row.get("GROSSLOANS"), 0) / 1e8, 4
                ) if safe_float(row.get("GROSSLOANS")) else None,
            })
    except Exception as e:
        logger.warning(f"[{stock_code}] bank indicators failed (non-bank OK): {e}")
    return records


def fetch_dividend(stock_code: str, stock_name: str) -> List[dict]:
    """dividend history from akshare

    akshare columns: ['公告日期', '送股', '转增', '派息', '进度', '除权除息日', '股权登记日', '红股上市日']
    Only keep records with a valid ex_date (skip '预案' stage entries).
    """
    records = []
    try:
        df = ak.stock_history_dividend_detail(symbol=stock_code, indicator="分红")
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            ex_date_raw = row.get("除权除息日")
            # skip NaT / None (preliminary/plan entries)
            if pd.isna(ex_date_raw) or not ex_date_raw:
                continue
            try:
                ex_date = pd.to_datetime(ex_date_raw).date()
            except Exception:
                continue

            cash_div = safe_float(row.get("派息"))

            record_date_raw = row.get("股权登记日")
            record_date = None
            if not pd.isna(record_date_raw) and record_date_raw:
                try:
                    record_date = pd.to_datetime(record_date_raw).date()
                except Exception:
                    pass

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "ex_date": ex_date,
                "record_date": record_date,
                "cash_div": cash_div,
                "div_total": None,
                "div_ratio": None,
            })
    except Exception as e:
        logger.error(f"[{stock_code}] dividend fetch failed: {e}")
    return records


def merge_bank_indicators(balance_records: List[dict], bank_records: List[dict]) -> List[dict]:
    """merge bank indicators into balance records by (stock_code, report_date)"""
    bank_map = {}
    for r in bank_records:
        key = (r["stock_code"], r["report_date"])
        bank_map[key] = r

    for rec in balance_records:
        key = (rec["stock_code"], rec["report_date"])
        if key in bank_map:
            bank = bank_map[key]
            rec["loan_total"] = bank.get("loan_total")
            rec["npl_ratio"] = bank.get("npl_ratio")
            rec["provision_coverage"] = bank.get("provision_coverage")
            rec["provision_ratio"] = bank.get("provision_ratio")
            rec["cap_adequacy_ratio"] = bank.get("cap_adequacy_ratio")
            rec["tier1_ratio"] = bank.get("tier1_ratio")
            rec["nim"] = bank.get("nim")
    return balance_records


def merge_roe_into_income(income_records: List[dict], bank_records: List[dict]) -> List[dict]:
    """backfill ROE from bank indicators into income records"""
    bank_map = {}
    for r in bank_records:
        key = (r["stock_code"], r["report_date"])
        bank_map[key] = r

    for rec in income_records:
        key = (rec["stock_code"], rec["report_date"])
        if key in bank_map:
            roe_val = bank_map[key].get("roe")
            if roe_val is not None:
                rec["roe"] = roe_val
    return income_records


def compute_provision_adj(storage: FinancialStorage, stock_code: str) -> List[dict]:
    """compute provision adjustment impact on profit (flitter method)"""
    rows = storage.query("""
        SELECT b.report_date,
               b.loan_total,
               b.provision_ratio,
               LAG(b.provision_ratio) OVER (PARTITION BY b.stock_code ORDER BY b.report_date) AS prev_ratio,
               LAG(b.loan_total) OVER (PARTITION BY b.stock_code ORDER BY b.report_date) AS prev_loan
        FROM financial_balance b
        WHERE b.stock_code = %s
        ORDER BY b.report_date
    """, (stock_code,))

    results = []
    for row in rows:
        if row["provision_ratio"] is None or row["prev_ratio"] is None:
            continue
        loan = row["loan_total"] or 0
        prev_loan = row["prev_loan"] or loan
        avg_loan = (loan + prev_loan) / 2

        ratio_change = (row["provision_ratio"] - row["prev_ratio"]) / 100
        provision_adj = ratio_change * avg_loan
        profit_adj_est = -provision_adj * 0.75

        results.append({
            "stock_code": stock_code,
            "stock_name": "",
            "report_date": row["report_date"],
            "provision_adj": round(provision_adj, 4),
            "profit_adj_est": round(profit_adj_est, 4),
        })
    logger.info(f"  [{stock_code}] provision adj: {len(results)} periods")
    return results


def run_fetch(config: FinancialFetcherConfig, stock_codes: Dict[str, str] = None,
              single_code: str = None, skip_init: bool = False) -> Dict[str, int]:
    """
    main entry: fetch all financial data for watch list
    Returns: {stock_code: records_saved_count}
    """
    targets = stock_codes or config.watch_list
    if single_code:
        targets = {single_code: targets.get(single_code, single_code)}

    storage = FinancialStorage(env=config.db_env)
    if not skip_init:
        storage.init_tables()

    stats = {}
    for code, name in targets.items():
        logger.info(f"===== {name} ({code}) =====")
        total = 0

        income = fetch_income(code, name)
        logger.info(f"  income: {len(income)} rows")
        time.sleep(config.request_interval)

        balance = fetch_balance(code, name)
        time.sleep(config.request_interval)

        bank = fetch_bank_indicators(code, name)
        if bank:
            balance = merge_bank_indicators(balance, bank)
            income = merge_roe_into_income(income, bank)
            logger.info(f"  bank indicators: {len(bank)} rows")
        if balance:
            storage.upsert("financial_balance", balance)
            total += len(balance)
        logger.info(f"  balance: {len(balance)} rows")

        # save income after ROE backfill from bank indicators
        if income:
            storage.upsert("financial_income", income)
            total += len(income)
        time.sleep(config.request_interval)

        div = fetch_dividend(code, name)
        if div:
            storage.upsert("financial_dividend", div)
            total += len(div)
        logger.info(f"  dividend: {len(div)} rows")
        time.sleep(config.request_interval)

        prov = compute_provision_adj(storage, code)
        if prov:
            storage.upsert("bank_asset_quality", prov)
            total += len(prov)

        stats[code] = total
        logger.info(f"===== {name} done: {total} rows =====\n")

    return stats
