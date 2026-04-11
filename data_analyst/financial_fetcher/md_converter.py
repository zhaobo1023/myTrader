# -*- coding: utf-8 -*-
"""
PDF -> Markdown converter for annual reports.

Uses pymupdf4llm (fast, already installed) with MinerU as optional upgrade.
Injects YAML frontmatter from filename for downstream metadata filtering.
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Filename pattern: {name}_{code}_{year}_{type}.pdf
# e.g. 华夏银行_600015_2025_年报.pdf
_FILENAME_RE = re.compile(
    r"(?P<name>.+?)_(?P<code>\d{5,6})_(?P<year>\d{4})_(?P<rtype>.+)\.(pdf|PDF)$"
)

_REPORT_TYPE_MAP = {
    "年报": "annual",
    "半年报": "semi",
    "一季报": "q1",
    "三季报": "q3",
}


def _parse_filename(filename: str) -> Optional[dict]:
    """Extract metadata from standard filename."""
    m = _FILENAME_RE.match(Path(filename).name)
    if not m:
        return None
    rtype_cn = m.group("rtype")
    return {
        "stock_name": m.group("name"),
        "stock_code": m.group("code"),
        "report_year": int(m.group("year")),
        "report_type": _REPORT_TYPE_MAP.get(rtype_cn, rtype_cn),
        "report_type_cn": rtype_cn,
    }


def _build_frontmatter(meta: dict) -> str:
    return (
        "---\n"
        f"stock_code: \"{meta['stock_code']}\"\n"
        f"stock_name: \"{meta['stock_name']}\"\n"
        f"report_year: {meta['report_year']}\n"
        f"report_type: \"{meta['report_type']}\"\n"
        f"source: \"{meta['stock_name']}_{meta['stock_code']}_{meta['report_year']}_{meta['report_type_cn']}\"\n"
        "---\n\n"
    )


def _convert_with_pymupdf4llm(pdf_path: str) -> str:
    """Convert PDF to markdown using pymupdf4llm."""
    import pymupdf4llm
    return pymupdf4llm.to_markdown(pdf_path)


def _convert_with_mineru(pdf_path: str, output_dir: str) -> str:
    """Convert PDF to markdown using MinerU CLI. Returns md content."""
    import subprocess
    import tempfile

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["mineru", "-p", pdf_path, "-o", str(out), "--lang", "ch"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MinerU failed: {result.stderr[:500]}")

    # MinerU outputs to {output_dir}/{pdf_stem}/{pdf_stem}.md
    pdf_stem = Path(pdf_path).stem
    candidates = list(out.rglob("*.md"))
    if not candidates:
        raise FileNotFoundError(f"MinerU produced no md file in {out}")
    # prefer the one matching the stem
    md_file = next((f for f in candidates if pdf_stem in f.name), candidates[0])
    return md_file.read_text(encoding="utf-8")


class MDConverter:
    """Convert annual report PDFs to Markdown with YAML frontmatter."""

    def __init__(self, prefer_mineru: bool = False):
        """
        Args:
            prefer_mineru: Use MinerU if available (better table accuracy).
                           Falls back to pymupdf4llm automatically.
        """
        self.prefer_mineru = prefer_mineru
        self._mineru_available = self._check_mineru()

    def _check_mineru(self) -> bool:
        try:
            import subprocess
            r = subprocess.run(["mineru", "--version"], capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def convert(self, pdf_path: str, output_dir: Optional[str] = None) -> str:
        """
        Convert a single PDF to Markdown.

        Returns the markdown content (with frontmatter injected).
        Also saves .md file alongside the PDF (or in output_dir).
        """
        pdf_path = str(pdf_path)
        meta = _parse_filename(pdf_path)

        if self.prefer_mineru and self._mineru_available:
            _tmp = output_dir or str(Path(pdf_path).parent / "md_tmp")
            md_content = _convert_with_mineru(pdf_path, _tmp)
            logger.info("[MDConverter] MinerU: %s", Path(pdf_path).name)
        else:
            md_content = _convert_with_pymupdf4llm(pdf_path)
            logger.info("[MDConverter] pymupdf4llm: %s", Path(pdf_path).name)

        if meta:
            md_content = _build_frontmatter(meta) + md_content

        # save
        out_dir = Path(output_dir) if output_dir else Path(pdf_path).parent / "md"
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / (Path(pdf_path).stem + ".md")
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("[MDConverter] Saved: %s (%d chars)", md_path, len(md_content))
        return md_content

    def batch_convert(
        self,
        pdf_dir: str,
        output_dir: Optional[str] = None,
        pattern: str = "*.pdf",
        skip_existing: bool = True,
    ) -> List[str]:
        """
        Batch convert all PDFs in a directory.

        Args:
            skip_existing: Skip if .md already exists in output_dir.

        Returns:
            List of output .md file paths.
        """
        pdf_dir = Path(pdf_dir)
        out_dir = Path(output_dir) if output_dir else pdf_dir / "md"
        out_dir.mkdir(parents=True, exist_ok=True)

        pdfs = sorted(pdf_dir.glob(pattern))
        if not pdfs:
            logger.warning("[MDConverter] No PDFs found in %s", pdf_dir)
            return []

        results = []
        for pdf in pdfs:
            md_path = out_dir / (pdf.stem + ".md")
            if skip_existing and md_path.exists():
                logger.info("[MDConverter] Skip (exists): %s", pdf.name)
                results.append(str(md_path))
                continue
            try:
                self.convert(str(pdf), str(out_dir))
                results.append(str(md_path))
            except Exception as e:
                logger.error("[MDConverter] Failed %s: %s", pdf.name, e)

        logger.info(
            "[MDConverter] batch done: %d/%d converted", len(results), len(pdfs)
        )
        return results
