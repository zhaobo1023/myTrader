# -*- coding: utf-8 -*-
"""
Bank annual report extraction template.

Extracts:
- Income statement: fee, investment income, fair value change, OCI
- Overdue loan detail: 1-90d, 91-360d, 361d-3y, 3y+, 90d+ total
- Restructured loans
- NPL ratio 2 (calculated)
- Cash flow summary
"""
import re
import logging
from typing import Dict, Optional

from .base_template import BaseTemplate, _clean_number, _unit_multiplier

logger = logging.getLogger(__name__)


class BankTemplate(BaseTemplate):
    """Extraction template for Chinese bank annual reports."""

    # ----------------------------------------------------------
    # Income Statement - Non-interest income section
    # ----------------------------------------------------------

    def extract_income_detail(self) -> Dict:
        """
        Extract non-interest income breakdown and OCI.
        Section: 非利息净收入 / 非利息收入
        """
        result = {}

        # Find the non-interest income section
        # Try table-bearing section titles first (e.g. "非利息收入主要构成")
        section = self.find_section(
            "非利息收入主要构成", "非利息净收入主要构成",
            "非利息净收入", "非利息收入", "非息净收入", "非息收入"
        )
        if not section:
            logger.warning("[BankTemplate] 非利息净收入 section not found")
            return result

        # detect unit from section text
        unit_hint = ""
        m = re.search(r"单位[：:]\s*([^\n）)]+)", section)
        if m:
            unit_hint = m.group(1)
        mult = _unit_multiplier(unit_hint)

        rows = self.parse_md_table(section)
        if not rows:
            logger.warning("[BankTemplate] No table found in 非利息净收入 section")
            return result

        # Map Chinese field names to schema columns
        # Note: 公允价值变动 may appear as 损益 or 收益 depending on year/profit sign
        field_map = {
            "手续费及佣金净收入": "fee_commission_net",
            "投资收益": "investment_income",
            "公允价值变动损益": "fair_value_change",
            "公允价值变动收益": "fair_value_change",
            "汇兑收益": "exchange_gain",
            "其他业务收入": "other_business_income",
            "合计": "non_interest_income_total",
        }

        # Determine the 'current year' column (first numeric column after item name)
        headers = list(rows[0].keys()) if rows else []
        # Typically: ['项目', '2025年', '2024年', '增减额', '增幅(%)']
        # We want the second column (index 1) = current year
        current_year_col = headers[1] if len(headers) > 1 else None

        for row in rows:
            item_col = headers[0] if headers else ""
            item_name = row.get(item_col, "")
            for cn_name, schema_col in field_map.items():
                if cn_name in item_name:
                    if current_year_col:
                        val = _clean_number(row.get(current_year_col, ""))
                    else:
                        # fallback: take second non-empty value
                        vals = [v for v in list(row.values())[1:] if v.strip()]
                        val = _clean_number(vals[0]) if vals else None
                    if val is not None:
                        result[schema_col] = val * mult
                    break

        # OCI: look for 其他综合收益 outside the income table
        oci_section = self.find_section("其他综合收益", "综合收益") or self.text
        oci_val = self.extract_inline_number(
            oci_section,
            r"其他综合收益[^\d\-（(]*([（(]?[\-]?[\d,]+\.?\d*[）)]?)\s*亿?元?",
        )
        if oci_val is None:
            # try from a table where row is 其他综合收益
            oci_rows = self.parse_md_table(oci_section) if oci_section else []
            oci_val = self.get_value_from_table(oci_rows, "其他综合收益", "")
        if oci_val is not None:
            result["other_comprehensive_income"] = oci_val

        logger.info("[BankTemplate] income_detail: %s", result)
        return result

    # ----------------------------------------------------------
    # Cash Flow Summary
    # ----------------------------------------------------------

    def extract_cashflow(self) -> Dict:
        """Extract operating / investing / financing cash flows."""
        result = {}

        # Strategy 1: prose descriptions with 亿元 values (primary - most reliable)
        # Variants:
        #   "经营活动产生的现金净流入XX亿元"
        #   "经营活动产生的现金流量净额为XX亿元，上年度为净流出..."
        #   "经营活动产生的现金净额XX亿元"
        prose_patterns = {
            "operating_cashflow": (
                r"经营活动产生的现金(?:净流[入出]|流量净额[^，。\d]*?(?:净流入)?)[^\d（(（]*([（(（]?[\d.]+[）)）]?)\s*亿",
                r"经营活动产生的现金(?:净(流入|流出)|流量净额)",
            ),
            "investing_cashflow": (
                r"投资活动产生的现金(?:净流[入出]|流量净额[^，。\d]*?(?:净流入)?)[^\d（(（]*([（(（]?[\d.]+[）)）]?)\s*亿",
                r"投资活动产生的现金(?:净(流入|流出)|流量净额)",
            ),
            "financing_cashflow": (
                r"筹资活动产生的现金(?:净流[入出]|流量净额[^，。\d]*?(?:净流入)?)[^\d（(（]*([（(（]?[\d.]+[）)）]?)\s*亿",
                r"筹资活动产生的现金(?:净(流入|流出)|流量净额)",
            ),
        }
        for schema_col, (pat, sign_pat) in prose_patterns.items():
            m_val = re.search(pat, self.text)
            if m_val:
                raw = m_val.group(1).replace("（", "").replace("）", "").replace("(", "").replace(")", "")
                try:
                    val = float(raw.replace(",", ""))
                except ValueError:
                    continue
                # Determine sign: look for 流出/净流出 in the matched context
                ctx = m_val.group(0)
                if "流出" in ctx and "净流入" not in ctx:
                    val = -val
                result[schema_col] = val

        # Strategy 2: table row pattern for operating cashflow fallback.
        # Detect actual unit from nearby "单位：XXX" declaration; default 百万元.
        if "operating_cashflow" not in result:
            m_unit = re.search(r"单位[：:]\s*([^\n）)（]+)", self.text)
            unit_hint = m_unit.group(1).strip() if m_unit else "百万元"
            mult = _unit_multiplier(unit_hint)
            val = self.extract_inline_number(
                self.text,
                r"经营活动产生的现金流量净额[^\d\-（(]*\|?\s*([\-（(]?[\d,]+\.?\d*[）)]?)",
            )
            if val is not None:
                result["operating_cashflow"] = val * mult

        logger.info("[BankTemplate] cashflow: %s", result)
        return result

    # ----------------------------------------------------------
    # Overdue Loan Detail (bank-specific)
    # ----------------------------------------------------------

    def extract_overdue_detail(self) -> Dict:
        """
        Extract overdue loan breakdown and restructured loans.
        Returns dict for bank_overdue_detail table.

        Note: The overdue table has a dual-header structure:
          Row1: | 项目 | 2025年末 | 2025年末 | 2024年末 | 2024年末 |
          Row2: |      | 余额     | 占比(%)  | 余额     | 占比(%)  |
        We extract the first "余额" column (2025年末 balance), unit=百万元 -> 亿.
        """
        result = {}

        # --- Overdue loan table ---
        section = self.find_section("逾期期限", "逾期贷款")
        if not section:
            logger.warning("[BankTemplate] 逾期贷款 section not found")
            return result

        # Detect unit (百万元 is standard for bank loan tables)
        unit_hint = "百万元"
        m = re.search(r"单位[：:]\s*([^\n）)（]+)", section)
        if m:
            unit_hint = m.group(1).strip()
        mult = _unit_multiplier(unit_hint)  # 百万元 -> 亿: 0.01

        # Use inline numbers from the text description as primary source
        # "逾期90天以内贷款和逾期90天以上贷款余额分别为132.44亿元和281.83亿元"
        # need second number after "和"
        m_both = re.search(
            r"逾期\s*90\s*天以内[^，。]*?(\d+\.?\d*)\s*亿[^，。]*?和\s*(\d+\.?\d*)\s*亿",
            section,
        )
        if m_both:
            result["overdue_90_plus"] = float(m_both.group(2))
        else:
            # fallback: direct match
            inline_90plus = self.extract_inline_number(
                section,
                r"逾期\s*90\s*天以上贷款余额[^，。]*?(\d+\.?\d*)\s*亿",
            )
            if inline_90plus:
                result["overdue_90_plus"] = inline_90plus

        inline_overdue_total = self.extract_inline_number(
            section,
            r"逾期贷款余额\s*(\d+\.?\d*)\s*亿",
        )
        if inline_overdue_total:
            result["overdue_total"] = inline_overdue_total

        # Parse the table for row-level breakdown
        # The table has structure: col0=项目, col1=2025年末余额, col2=2025年末占比, ...
        # After parse_md_table, headers are the first row including empty strings
        # We'll parse raw lines to handle dual-header correctly
        rows_raw = self._parse_overdue_table_raw(section, mult)
        for field, val in rows_raw.items():
            if field not in result:  # inline values take priority
                result[field] = val

        # --- Official NPL from 不良贷款 section ---
        npl_section = self.find_section("不良贷款", "贷款五级分类")
        if npl_section:
            # inline: "不良贷款余额398.86亿元，不良贷款率1.554%"
            npl_balance = self.extract_inline_number(
                npl_section,
                r"不良贷款余额\s*(\d+\.?\d*)\s*亿",
            )
            if npl_balance:
                result["official_npl"] = npl_balance

            # Use a context-aware pattern: match 不良贷款率 only when preceded by 整体/本集团/合计
            # to avoid matching sub-segment ratios (个人贷款不良率 2.11%, 小微 1.64% etc.)
            npl_ratio = self.extract_inline_number(
                npl_section,
                r"(?:本集团|集团整体|合计|全行)?不良贷款率\s*([\d.]+)\s*%(?!.*个人|.*小微|.*公房|.*住房)",
            )
            # Fallback: find the ratio that appears right after "不良贷款余额XXX亿元"
            if npl_ratio is None:
                npl_ratio = self.extract_inline_number(
                    npl_section,
                    r"不良贷款余额\s*\d+\.?\d*\s*亿[元]?[^。]*?不良贷款率\s*([\d.]+)\s*%",
                )
            if npl_ratio:
                result["official_npl_ratio"] = npl_ratio

        # official_npl_ratio from Markdown may still be unreliable; see run() for DB fallback

        # --- Total loans ---
        if "total_loans" not in result:
            # Try section first, then fall back to full document
            # inline: "贷款总额25,666.66亿元"
            total = self.extract_inline_number(
                section,
                r"贷款总额[^\d]*?([\d,]+\.?\d*)\s*亿",
            ) or self.extract_inline_number(
                self.text,
                r"贷款总额[^\d]*?([\d,]+\.?\d*)\s*亿",
            )
            if total:
                result["total_loans"] = total

        # --- Restructured loans ---
        restructured_section = self.find_section("重组贷款")
        if restructured_section:
            val = self.extract_inline_number(
                restructured_section,
                r"重组贷款账面余额\s*([\d.]+)\s*亿",
            )
            if val is not None:
                result["restructured"] = val
            else:
                # parse table (unit: 百万元)
                rs_unit = "百万元"
                rs_m = re.search(r"单位[：:]\s*([^\n）)（]+)", restructured_section)
                if rs_m:
                    rs_unit = rs_m.group(1).strip()
                rs_mult = _unit_multiplier(rs_unit)
                rs_rows = self.parse_md_table(restructured_section)
                rs_headers = list(rs_rows[0].keys()) if rs_rows else []
                # find 余额 column
                balance_col = next(
                    (h for h in rs_headers if "余额" in h or "金额" in h),
                    rs_headers[1] if len(rs_headers) > 1 else None,
                )
                for row in rs_rows:
                    item_col = rs_headers[0] if rs_headers else ""
                    if "重组贷款" in row.get(item_col, ""):
                        if balance_col:
                            v = _clean_number(row.get(balance_col, ""))
                            if v is not None:
                                result["restructured"] = v * rs_mult
                        break

        # --- Compute NPL ratio 2 ---
        overdue_90 = result.get("overdue_90_plus")
        restructured = result.get("restructured")
        total = result.get("total_loans")
        if overdue_90 is not None and restructured is not None and total and total > 0:
            result["npl_ratio2"] = (overdue_90 + restructured) / total * 100

        # --- overdue90+ / official_npl coverage ---
        official_npl = result.get("official_npl")
        if overdue_90 is not None and official_npl and official_npl > 0:
            result["overdue90_npl_coverage"] = overdue_90 / official_npl * 100

        logger.info("[BankTemplate] overdue_detail: %s", result)
        return result

    def _parse_overdue_table_raw(self, section: str, mult: float) -> Dict:
        """
        Parse the dual-header overdue table directly.
        The table layout in Markdown:
          | 项目 | 2025年末 | 2025年末 | 2024年末 | 2024年末 |
          |---|...|
          |  | 余额 | 占比(%) | 余额 | 占比(%) |   <- second header row
          | 正常贷款 | 2,525,239 | ... |
          ...
        We want: col1 = 2025年末 余额 (index 1)

        Auto-detects unit from table magnitude when no explicit 单位 declaration:
          - values >= 1e7 → assume 元 (mult = 1e-8)
          - values >= 1e4 → assume 千元 (mult = 1e-5), rare
          - otherwise     → use caller-supplied mult (default 百万元 = 0.01)
        """
        result = {}
        lines = [l.strip() for l in section.split("\n") if l.strip()]
        table_lines = [l for l in lines if l.startswith("|")]
        if len(table_lines) < 3:
            return result

        # Skip header rows and separator (lines with only |---|---|)
        data_lines = []
        seen_sep = False
        skip_header2 = False
        for line in table_lines:
            if re.match(r"^\|[\s\-|:]+\|$", line):
                seen_sep = True
                continue
            if not seen_sep:
                continue
            # skip second header row (all non-numeric or contains 余额/占比)
            cells = [c.strip() for c in line.strip("|").split("|")]
            cells = [re.sub(r"\*+", "", c).strip() for c in cells]
            if not skip_header2 and any(
                kw in "".join(cells) for kw in ["余额", "占比", "金额"]
            ):
                skip_header2 = True
                continue
            data_lines.append(cells)

        # Auto-detect unit from first numeric value in the table.
        # If the raw number is >= 1e7, the table is denominated in 元.
        # If >= 500 (百万元 would give value in range 500-50000 for a ~10亿 bank), keep mult.
        effective_mult = mult
        for cells in data_lines:
            if len(cells) > 1:
                v = _clean_number(cells[1])
                if v is not None and abs(v) > 0:
                    if abs(v) >= 1e7:
                        effective_mult = 1e-8   # 元 -> 亿
                    elif abs(v) >= 1e4 and mult == 0.01:
                        # Likely 千元 when default百万元 doesn't fit
                        effective_mult = 1e-5
                    break

        field_map = {
            "逾期1": "overdue_1_90",
            "逾期91": "overdue_91_360",
            "逾期361": "overdue_361_3y",
            "逾期3年以上": "overdue_3y_plus",
            "逾期90": "overdue_90_plus",
            "逾期贷款": "overdue_total",
            "合计": "overdue_total",   # 合计 = total overdue subtotal, NOT total loan book
        }

        for cells in data_lines:
            if not cells or not cells[0]:
                continue
            item = cells[0]
            # Get first balance column (index 1)
            balance_val = cells[1] if len(cells) > 1 else ""
            val = _clean_number(balance_val)
            if val is None:
                continue
            for cn_key, schema_col in field_map.items():
                if cn_key in item:
                    result[schema_col] = val * effective_mult
                    break

        return result

    # ----------------------------------------------------------
    # Run all
    # ----------------------------------------------------------

    def run(self, stock_code: str, stock_name: str, report_date: str) -> Dict:
        base = super().run(stock_code, stock_name, report_date)

        # Extract cashflow separately so _save_results doesn't need to mutate income_detail
        cashflow = self.extract_cashflow()
        cashflow.update({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_date": report_date,
        })

        overdue = self.extract_overdue_detail()
        overdue.update({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_date": report_date,
        })

        # official_npl_ratio: prefer Markdown extraction (精确到3位小数) over AKShare (2位小数)
        # Only fall back to AKShare if Markdown extraction failed entirely
        if not overdue.get("official_npl_ratio"):
            try:
                from config.db import execute_query
                fb_rows = execute_query(
                    "SELECT npl_ratio FROM financial_balance WHERE stock_code=%s AND report_date=%s LIMIT 1",
                    params=(stock_code, report_date),
                    env="online",
                )
                if fb_rows and fb_rows[0].get("npl_ratio"):
                    overdue["official_npl_ratio"] = float(fb_rows[0]["npl_ratio"])
            except Exception:
                pass

        # Recompute derived fields after official_npl_ratio override
        ov90 = overdue.get("overdue_90_plus")
        rs = overdue.get("restructured")
        total = overdue.get("total_loans")
        npl_off = overdue.get("official_npl_ratio")
        if ov90 is not None and rs is not None and total and total > 0:
            overdue["npl_ratio2"] = (ov90 + rs) / total * 100
        if ov90 is not None and overdue.get("official_npl") and overdue["official_npl"] > 0:
            overdue["overdue90_npl_coverage"] = ov90 / overdue["official_npl"] * 100
        return {
            "income_detail": base,
            "cashflow_detail": cashflow,
            "overdue_detail": overdue,
        }
