# -*- coding: utf-8 -*-
"""
AKShare Financial Data Loader

Fetches A-share financial summary data for use in research report LLM analysis.

Data sources:
1. stock_financial_abstract: ratios (ROE/gross margin/growth rates) - no absolute values
2. stock_profit_sheet_by_report_em: income statement with actual amounts in yuan
   -> converted to 亿元 with explicit unit labels to prevent LLM unit confusion

Design note: AKShare income statement returns values in yuan (元). All absolute
values are divided by 1e8 and labeled as 亿元 to prevent LLM from confusing
万元 / 亿元 quantities. This is the primary guard against magnitude hallucination.
"""
import logging
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

# Columns we want from the income statement, mapped to display labels
_INCOME_COLS = {
    "营业收入": "营业收入",
    "利息净收入": "利息净收入(银行)",
    "手续费及佣金净收入": "手续费净收入(银行)",
    "营业支出": "营业支出",
    "信用减值损失": "信用减值损失",
    "公允价值变动收益": "公允价值变动损益",
    "投资收益": "投资收益",
    "营业利润": "营业利润",
    "利润总额": "利润总额",
    "净利润": "净利润",
    "归属于母公司股东的净利润": "归母净利润",
}


class AKShareLoader:
    """Load financial summary data from AKShare."""

    def get_financial_data(self, stock_code: str, years: int = 3) -> Dict[str, Any]:
        """
        Get financial summary for a stock: ratios + income statement absolute values.

        Args:
            stock_code: Pure numeric code, e.g. "000858" (no market suffix)
            years: Number of years (affects record count)

        Returns:
            {
                "raw": dict,        # raw parsed result
                "summary": str,     # formatted LLM-readable text
                "error": str|None   # None on success
            }
        """
        parts = []
        errors = []

        # 1. Ratio data (ROE, gross margin, growth rates)
        try:
            raw = self._fetch_financial_abstract(stock_code)
            ratio_summary = self._format_ratio_summary(raw, stock_code=stock_code, years=years)
            if ratio_summary:
                parts.append(ratio_summary)
        except Exception as e:
            logger.warning("[AKShareLoader] ratio data failed for %s: %s", stock_code, e)
            errors.append(f"ratio: {e}")

        # 2. Income statement absolute values (the critical fix for magnitude hallucination)
        try:
            income_summary = self._fetch_income_statement(stock_code, periods=years * 2)
            if income_summary:
                parts.append(income_summary)
        except Exception as e:
            logger.warning("[AKShareLoader] income statement failed for %s: %s", stock_code, e)
            errors.append(f"income_stmt: {e}")

        summary = "\n\n".join(parts) if parts else ""
        error_str = "; ".join(errors) if errors else None

        if not summary:
            summary = f"[Financial Data] {stock_code} no data available"
            if error_str:
                summary += f" (errors: {error_str})"

        return {"raw": {}, "summary": summary, "error": error_str}

    def _fetch_financial_abstract(self, stock_code: str) -> Dict[str, Any]:
        """Call AKShare to get financial abstract (ROE/gross margin/growth rates etc.)"""
        df = ak.stock_financial_abstract(symbol=stock_code)
        if df is None or df.empty:
            return {}
        records = df.head(16).to_dict(orient="records")
        return {"records": records, "columns": list(df.columns)}

    def _format_ratio_summary(
        self,
        data: Dict[str, Any],
        stock_code: str = "",
        years: int = 3,
    ) -> str:
        """Format ratio data into LLM-readable text (ROE/growth/margins only, no absolute values)."""
        if not data or "records" not in data:
            return ""

        records = data.get("records", [])
        if not records:
            return ""

        max_records = years * 4  # quarterly: ~4 records per year
        lines = [
            f"[财务比率摘要 - AKShare] 股票: {stock_code}，"
            f"最近 {min(len(records), max_records)} 期（均为比率/增速，无绝对金额）:"
        ]

        for i, rec in enumerate(records[:max_records]):
            row_parts = []
            for k, v in rec.items():
                if v is not None and str(v).strip() not in ("", "nan", "None"):
                    row_parts.append(f"{k}={v}")
            if row_parts:
                lines.append(f"  期 {i + 1}: " + ", ".join(row_parts))

        return "\n".join(lines)

    def _fetch_income_statement(self, stock_code: str, periods: int = 6) -> str:
        """
        Fetch income statement with actual amounts from East Money (AKShare).

        Values are in yuan (元) in the raw data. This method converts to 亿元
        and adds explicit unit labels. This is the primary defense against
        LLM magnitude hallucination (confusing 万元 with 亿元).

        Returns:
            Formatted string with amounts labeled as 亿元, or empty string on failure.
        """
        try:
            df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
        except Exception as e:
            logger.warning(
                "[AKShareLoader] stock_profit_sheet_by_report_em failed for %s: %s",
                stock_code, e,
            )
            return ""

        if df is None or df.empty:
            return ""

        # The first column is typically the item name; remaining columns are periods
        # Row index = financial item names, columns = report dates
        try:
            df = df.set_index(df.columns[0])
        except Exception:
            pass

        # Select up to `periods` most recent columns
        date_cols = [c for c in df.columns if str(c).strip()]
        date_cols = date_cols[:periods]

        if not date_cols:
            return ""

        lines = [
            f"[利润表绝对值 - AKShare东方财富] 股票: {stock_code}，"
            f"单位: 亿元（原始数据单位为元，已除以1亿换算）。"
            f"警告：所有下列数字均已明确换算为亿元，请勿再次换算。"
        ]
        lines.append(f"报告期: {' | '.join(str(c) for c in date_cols)}")
        lines.append("-" * 60)

        for raw_name, display_name in _INCOME_COLS.items():
            # Try to find the row (exact or partial match)
            row = self._find_row(df, raw_name)
            if row is None:
                continue

            values = []
            for col in date_cols:
                val = row.get(col)
                converted = self._to_yi(val)
                values.append(f"{converted:>10.2f}亿" if converted is not None else f"{'N/A':>10}")

            lines.append(f"{display_name:<20}: {' | '.join(values)}")

        if len(lines) <= 3:
            return ""

        lines.append(
            "\n注：以上为利润表关键科目绝对值，单位亿元已确认。"
            "分析时请直接使用上述数字，无需估算。"
        )
        return "\n".join(lines)

    def _find_row(self, df: pd.DataFrame, name: str) -> Optional[Dict]:
        """Find a row by exact or partial index match, return as dict {col: value}."""
        if name in df.index:
            return df.loc[name].to_dict()
        # Partial match
        for idx in df.index:
            if isinstance(idx, str) and name in idx:
                return df.loc[idx].to_dict()
        return None

    @staticmethod
    def _to_yi(val) -> Optional[float]:
        """Convert yuan (元) value to 亿元. Returns None if not numeric."""
        if val is None:
            return None
        try:
            f = float(val)
            if f != f:  # NaN
                return None
            return f / 1e8
        except (TypeError, ValueError):
            return None
