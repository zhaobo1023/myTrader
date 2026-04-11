# -*- coding: utf-8 -*-
"""
Annual Report Extractor - 年报结构化数据提取入口

Flow:
  PDF --[MDConverter]--> .md file
    --> [BankTemplate / GeneralTemplate] --> structured dicts
    --> [FinancialStorage.upsert()] --> MySQL tables

Usage:
    # Single file
    extractor = AnnualReportExtractor()
    extractor.extract_and_save("600015", "华夏银行", "2025-12-31",
                               md_path="path/to/华夏银行_2025_年报.md")

    # Auto: PDF -> MD -> extract -> save
    extractor.process_pdf(
        pdf_path="path/to/华夏银行_600015_2025_年报.pdf",
        industry="bank"
    )

    # Batch directory
    extractor.batch_process_dir(
        pdf_dir="/path/to/annual_reports/600015/",
        industry="bank"
    )
"""
import logging
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Map report_type -> typical report_date suffix
_REPORT_DATE_MAP = {
    "annual": "12-31",
    "semi": "06-30",
    "q1": "03-31",
    "q3": "09-30",
}

# Filename pattern: {name}_{code}_{year}_{type}.pdf or .md
_FNAME_RE = re.compile(
    r"(?P<name>.+?)_(?P<code>\d{5,6})_(?P<year>\d{4})_(?P<rtype>.+)\.(pdf|PDF|md)$"
)
_CN_TYPE_MAP = {
    "年报": "annual", "半年报": "semi",
    "一季报": "q1", "三季报": "q3",
}


def _infer_meta_from_path(path: str) -> Optional[Dict]:
    m = _FNAME_RE.match(Path(path).name)
    if not m:
        return None
    rtype_cn = m.group("rtype")
    rtype = _CN_TYPE_MAP.get(rtype_cn, rtype_cn)
    year = int(m.group("year"))
    date_suffix = _REPORT_DATE_MAP.get(rtype, "12-31")
    return {
        "stock_name": m.group("name"),
        "stock_code": m.group("code"),
        "report_year": year,
        "report_type": rtype,
        "report_date": f"{year}-{date_suffix}",
    }


class AnnualReportExtractor:
    """Extract structured financial data from annual report Markdown files."""

    def __init__(self, db_env: str = "online", prefer_mineru: bool = False):
        from data_analyst.financial_fetcher.storage import FinancialStorage
        self._storage = FinancialStorage(env=db_env)
        self._prefer_mineru = prefer_mineru

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def process_pdf(
        self,
        pdf_path: str,
        industry: str = "bank",
        save: bool = True,
    ) -> Dict:
        """
        Full pipeline: PDF -> MD -> extract -> (save).

        Args:
            pdf_path: Path to annual report PDF.
            industry: "bank" or "general".
            save: Whether to write results to database.

        Returns:
            Extracted data dict.
        """
        from data_analyst.financial_fetcher.md_converter import MDConverter

        conv = MDConverter(prefer_mineru=self._prefer_mineru)
        md_dir = str(Path(pdf_path).parent / "md")
        md_content = conv.convert(pdf_path, output_dir=md_dir)
        meta = _infer_meta_from_path(pdf_path)
        if not meta:
            raise ValueError(f"Cannot parse filename: {Path(pdf_path).name}")

        return self.extract_and_save(
            stock_code=meta["stock_code"],
            stock_name=meta["stock_name"],
            report_date=meta["report_date"],
            md_content=md_content,
            industry=industry,
            save=save,
        )

    def process_md(
        self,
        md_path: str,
        industry: str = "bank",
        save: bool = True,
    ) -> Dict:
        """Process a pre-converted .md file."""
        md_content = Path(md_path).read_text(encoding="utf-8")

        # Try to get meta from frontmatter or filename
        meta = self._parse_frontmatter(md_content) or _infer_meta_from_path(md_path)
        if not meta:
            raise ValueError(f"Cannot determine metadata for: {md_path}")

        return self.extract_and_save(
            stock_code=meta["stock_code"],
            stock_name=meta["stock_name"],
            report_date=meta.get("report_date", f"{meta['report_year']}-12-31"),
            md_content=md_content,
            industry=industry,
            save=save,
        )

    def extract_and_save(
        self,
        stock_code: str,
        stock_name: str,
        report_date: str,
        md_path: Optional[str] = None,
        md_content: Optional[str] = None,
        industry: str = "bank",
        save: bool = True,
    ) -> Dict:
        """
        Extract from md content and optionally save to DB.
        Provide either md_path or md_content.
        """
        if md_content is None and md_path:
            md_content = Path(md_path).read_text(encoding="utf-8")
        if not md_content:
            raise ValueError("md_content or md_path required")

        template = self._get_template(industry, md_content)
        result = template.run(stock_code, stock_name, report_date)

        if save:
            self._save_results(result, industry)

        return result

    def batch_process_dir(
        self,
        pdf_dir: str,
        industry: str = "bank",
        save: bool = True,
        skip_existing: bool = True,
    ) -> List[Dict]:
        """Batch process all PDFs in a directory."""
        pdf_dir = Path(pdf_dir)
        results = []
        for pdf in sorted(pdf_dir.glob("*.pdf")):
            try:
                logger.info("[Extractor] Processing: %s", pdf.name)
                r = self.process_pdf(str(pdf), industry=industry, save=save)
                results.append(r)
            except Exception as e:
                logger.error("[Extractor] Failed %s: %s", pdf.name, e)
        return results

    def init_tables(self):
        """Create new tables if they don't exist."""
        self._storage.init_tables()
        logger.info("[Extractor] Tables initialized")

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _get_template(self, industry: str, md_content: str):
        if industry == "bank":
            from data_analyst.financial_fetcher.extraction_templates.bank_template import BankTemplate
            return BankTemplate(md_content)
        else:
            from data_analyst.financial_fetcher.extraction_templates.base_template import BaseTemplate
            return BaseTemplate(md_content)

    def _save_results(self, result: Dict, industry: str):
        """Write extracted data to appropriate tables."""
        if industry == "bank":
            income = result.get("income_detail", {})
            overdue = result.get("overdue_detail", {})
            # cashflow_detail is a separate key produced by BankTemplate.run()
            # (never mutate income_detail to avoid side-effects on the caller's dict)
            cashflow = dict(result.get("cashflow_detail", {}))
            if not cashflow.get("source"):
                cashflow["source"] = "annual_report"
            cashflow = {k: v for k, v in cashflow.items() if v is not None}

            if any(k not in ("stock_code", "stock_name", "report_date") for k in income):
                income["source"] = "annual_report"
                self._storage.upsert("financial_income_detail", [income])
                logger.info("[Extractor] Saved income_detail for %s %s",
                            income.get("stock_code"), income.get("report_date"))

            if any(k not in ("stock_code", "stock_name", "report_date") for k in overdue):
                overdue["source"] = "annual_report"
                self._storage.upsert("bank_overdue_detail", [overdue])
                logger.info("[Extractor] Saved bank_overdue_detail for %s %s",
                            overdue.get("stock_code"), overdue.get("report_date"))

            if any(v is not None for k, v in cashflow.items()
                   if k not in ("stock_code", "stock_name", "report_date", "source")):
                self._storage.upsert("financial_cashflow", [cashflow])
                logger.info("[Extractor] Saved financial_cashflow for %s %s",
                            cashflow.get("stock_code"), cashflow.get("report_date"))
        else:
            # general template: result is flat dict
            result["source"] = "annual_report"
            self._storage.upsert("financial_income_detail", [result])

    @staticmethod
    def _parse_frontmatter(md_content: str) -> Optional[Dict]:
        """Extract YAML frontmatter metadata."""
        m = re.match(r"^---\n(.+?)\n---", md_content, re.DOTALL)
        if not m:
            return None
        meta = {}
        for line in m.group(1).split("\n"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().strip('"\'')
                meta[key] = int(val) if val.isdigit() else val
        # compute report_date from year + type
        if "report_year" in meta and "report_type" in meta:
            suffix = _REPORT_DATE_MAP.get(meta["report_type"], "12-31")
            meta["report_date"] = f"{meta['report_year']}-{suffix}"
        return meta if "stock_code" in meta else None
