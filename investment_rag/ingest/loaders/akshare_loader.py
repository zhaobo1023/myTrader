# -*- coding: utf-8 -*-
"""
AKShare Financial Data Loader

Fetches A-share financial summary data (ROE/gross margin/profit growth/revenue growth)
for use in research report LLM analysis steps.
"""
import logging
from typing import Any, Dict

import akshare as ak

logger = logging.getLogger(__name__)


class AKShareLoader:
    """Load financial summary data from AKShare."""

    def get_financial_data(self, stock_code: str, years: int = 3) -> Dict[str, Any]:
        """
        Get financial summary for a stock.

        Args:
            stock_code: Pure numeric code, e.g. "000858" (no market suffix)
            years: Number of years (affects record count: ~4 records/year for quarterly)

        Returns:
            {
                "raw": dict,        # raw parsed result
                "summary": str,     # formatted LLM-readable text
                "error": str|None   # None on success
            }
        """
        try:
            raw = self._fetch_financial_abstract(stock_code)
            summary = self._format_summary(raw, stock_code=stock_code, years=years)
            return {"raw": raw, "summary": summary, "error": None}
        except Exception as e:
            logger.warning("[AKShareLoader] get_financial_data failed for %s: %s", stock_code, e)
            return {"raw": {}, "summary": "", "error": str(e)}

    def _fetch_financial_abstract(self, stock_code: str) -> Dict[str, Any]:
        """Call AKShare to get financial abstract (ROE/gross margin/profit growth etc.)"""
        df = ak.stock_financial_abstract(symbol=stock_code)
        if df is None or df.empty:
            return {}
        records = df.head(16).to_dict(orient="records")
        return {"records": records, "columns": list(df.columns)}

    def _format_summary(
        self,
        data: Dict[str, Any],
        stock_code: str = "",
        years: int = 3,
    ) -> str:
        """Format financial data into LLM-readable text."""
        if not data or "records" not in data:
            return f"[Financial Data] {stock_code} no financial summary available"

        records = data.get("records", [])
        if not records:
            return f"[Financial Data] {stock_code} financial summary is empty"

        max_records = years * 4  # quarterly: ~4 records per year
        lines = [
            f"[Financial Summary] Stock: {stock_code}, "
            f"latest {min(len(records), max_records)} periods:"
        ]

        for i, rec in enumerate(records[:max_records]):
            row_parts = []
            for k, v in rec.items():
                if v is not None and str(v).strip() not in ("", "nan", "None"):
                    row_parts.append(f"{k}={v}")
            if row_parts:
                lines.append(f"  Period {i + 1}: " + ", ".join(row_parts))

        return "\n".join(lines)
