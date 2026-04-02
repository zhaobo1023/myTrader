# -*- coding: utf-8 -*-
"""generate Markdown financial summary"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .storage import FinancialStorage

logger = logging.getLogger(__name__)


def _fmt(val, decimals=2):
    """format number for Markdown table"""
    if val is None:
        return "-"
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


def generate_markdown(stock_code: str, stock_name: str,
                      storage: FinancialStorage,
                      output_dir: str) -> Optional[str]:
    """generate Markdown financial summary for a stock"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("---")
    lines.append(f"tags: [financial, company/{stock_name}]")
    lines.append(f"stock_code: {stock_code}")
    lines.append(f"updated: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {stock_name} ({stock_code}) Financial Summary")
    lines.append("")

    # income
    lines.append("## Income Statement (Net Profit, yi)")
    lines.append("")
    rows = storage.query("""
        SELECT report_date, report_type, revenue, net_profit,
               net_profit_yoy, eps, roe
        FROM financial_income
        WHERE stock_code = %s
        ORDER BY report_date DESC LIMIT 16
    """, (stock_code,))

    if rows:
        lines.append("| Period | Type | Revenue(yi) | Net Profit(yi) | YoY% | EPS | ROE% |")
        lines.append("|--------|------|------------|---------------|------|-----|------|")
        for r in rows:
            lines.append(
                f"| {r['report_date']} | {r['report_type'] or '-'} "
                f"| {_fmt(r['revenue'])} | {_fmt(r['net_profit'])} "
                f"| {_fmt(r['net_profit_yoy'])} | {_fmt(r['eps'])} | {_fmt(r['roe'])} |"
            )
    lines.append("")

    # bank indicators
    lines.append("## Bank Indicators")
    lines.append("")
    rows = storage.query("""
        SELECT report_date, npl_ratio, provision_coverage,
               provision_ratio, cap_adequacy_ratio, tier1_ratio, nim
        FROM financial_balance
        WHERE stock_code = %s AND npl_ratio IS NOT NULL
        ORDER BY report_date DESC LIMIT 12
    """, (stock_code,))

    if rows:
        lines.append("| Period | NPL% | ProvCov% | LoanProv% | CAR% | Tier1% | NIM% |")
        lines.append("|--------|------|---------|----------|------|--------|------|")
        for r in rows:
            lines.append(
                f"| {r['report_date']} | {_fmt(r['npl_ratio'])} "
                f"| {_fmt(r['provision_coverage'])} | {_fmt(r['provision_ratio'])} "
                f"| {_fmt(r['cap_adequacy_ratio'])} | {_fmt(r['tier1_ratio'])} "
                f"| {_fmt(r['nim'])} |"
            )
    lines.append("")

    # provision adjustment
    lines.append("## Provision Adjustment (flitter method)")
    lines.append("")
    lines.append("> Positive = conservative (hiding profit). Negative = releasing (beautifying profit).")
    lines.append("")
    rows = storage.query("""
        SELECT report_date, provision_adj, profit_adj_est
        FROM bank_asset_quality
        WHERE stock_code = %s
        ORDER BY report_date DESC LIMIT 8
    """, (stock_code,))

    if rows:
        lines.append("| Period | Prov Adj(yi) | Profit Impact(yi) | Direction |")
        lines.append("|--------|-------------|------------------|-----------|")
        for r in rows:
            if r["provision_adj"] is None:
                continue
            direction = "[UP] conservative" if r["provision_adj"] > 0 else "[DOWN] releasing"
            lines.append(
                f"| {r['report_date']} | {_fmt(r['provision_adj'], 4)} "
                f"| {_fmt(r['profit_adj_est'], 4)} | {direction} |"
            )
    lines.append("")

    # dividend
    lines.append("## Dividend History")
    lines.append("")
    rows = storage.query("""
        SELECT ex_date, cash_div, div_total, div_ratio
        FROM financial_dividend
        WHERE stock_code = %s
        ORDER BY ex_date DESC LIMIT 10
    """, (stock_code,))

    if rows:
        lines.append("| Ex-Date | Per Share(yuan,pre-tax) | Total(yi) | Payout% |")
        lines.append("|--------|----------------------|----------|--------|")
        for r in rows:
            lines.append(
                f"| {r['ex_date'] or '-'} | {_fmt(r['cash_div'])} "
                f"| {_fmt(r['div_total'])} | {_fmt(r['div_ratio'])} |"
            )
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- Source: akshare (east money API)")
    lines.append("- Units: amounts in yi, ratios in %")
    lines.append(f"- Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    content = "\n".join(lines)
    filename = f"{stock_name}_{stock_code}_financial_summary.md"
    filepath = output_path / filename
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Markdown saved: {filepath}")
    return str(filepath)
