# -*- coding: utf-8 -*-
"""
Base extraction template for annual report Markdown files.

Provides:
- Markdown table parser
- Section locator (by heading keyword)
- Number cleaning utilities
"""
import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Match a Markdown table row: | val | val | ...
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
# Separator row: |---|---|
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-|:]+\|\s*$")
# Markdown heading: ## text
_HEADING_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)


def _clean_number(s: str) -> Optional[float]:
    """
    Convert a string to float, handling:
    - commas: "1,234" -> 1234
    - negatives with Chinese dash or minus: "-3,535", "（3,535）"
    - bold markers: "**28,183**"
    - percentage sign (removed, not divided)
    - empty / dash / N/A -> None
    """
    s = s.strip()
    # strip bold / italic markdown markers
    s = re.sub(r"\*+", "", s)
    s = s.strip()
    if not s or s in ("-", "—", "N/A", "n/a", "/"):
        return None
    # handle bracketed negatives: （3,535） -> -3535
    m = re.match(r"[（(]([0-9,]+(?:\.[0-9]+)?)[）)]", s)
    if m:
        return -float(m.group(1).replace(",", ""))
    # remove commas, percentage
    s = s.replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def _unit_multiplier(unit_hint: str) -> float:
    """Return multiplier to convert to yi (亿).

    Recognized unit strings (case-insensitive):
      亿元 / 亿       -> 1.0
      百万元 / million -> 0.01   (1百万 = 0.01亿)
      千元 / 千        -> 1e-5   (1千 = 0.00001亿)
      万元 / 万        -> 1e-4   (1万 = 0.0001亿)
      元               -> 1e-8   (1元 = 0.00000001亿)
    """
    hint = unit_hint.strip()
    if "亿" in hint:
        return 1.0
    if "百万" in hint or "million" in hint.lower():
        return 0.01
    if "千" in hint:
        return 1e-5   # 千元 -> 亿元
    if "万" in hint:
        return 1e-4   # 万元 -> 亿元
    if "元" in hint:
        return 1e-8   # 纯元 -> 亿元
    # unspecified: assume already in 亿
    return 1.0


class BaseTemplate:
    """Base class for annual report extraction templates."""

    def __init__(self, md_content: str):
        self.text = md_content
        self._sections: Optional[Dict[str, Tuple[int, int]]] = None

    # ----------------------------------------------------------
    # Section Locator
    # ----------------------------------------------------------

    def _build_section_index(self) -> Dict[str, Tuple[int, int]]:
        """Index all ## headings with their start/end char positions."""
        sections = {}
        matches = list(_HEADING_RE.finditer(self.text))
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            # strip markdown bold from title
            title_clean = re.sub(r"\*+", "", title).strip()
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(self.text)
            sections[title_clean] = (start, end)
        return sections

    def find_section(self, *keywords: str) -> Optional[str]:
        """
        Return the text of the first section whose title contains any keyword.
        Falls back to a substring search in the full document.
        """
        if self._sections is None:
            self._sections = self._build_section_index()

        for kw in keywords:
            for title, (s, e) in self._sections.items():
                if kw in title:
                    return self.text[s:e]

        # fallback: find keyword in full text, return surrounding ~2000 chars
        for kw in keywords:
            idx = self.text.find(kw)
            if idx >= 0:
                return self.text[max(0, idx - 100): idx + 2000]
        return None

    # ----------------------------------------------------------
    # Markdown Table Parser
    # ----------------------------------------------------------

    def parse_md_table(self, text: str) -> List[Dict[str, str]]:
        """
        Parse the first Markdown table found in text.

        Returns a list of dicts: {header: value, ...} per data row.
        Column headers from the first non-separator row.
        """
        lines = text.split("\n")
        headers: List[str] = []
        rows: List[Dict[str, str]] = []
        in_table = False

        for line in lines:
            if _TABLE_SEP_RE.match(line):
                in_table = True
                continue
            m = _TABLE_ROW_RE.match(line)
            if not m:
                if in_table and rows:
                    break  # table ended
                continue

            cells = [c.strip() for c in m.group(1).split("|")]
            # strip bold markers from cells
            cells = [re.sub(r"\*+", "", c).strip() for c in cells]

            if not headers:
                headers = cells
            elif in_table:
                row = {}
                for i, h in enumerate(headers):
                    row[h] = cells[i] if i < len(cells) else ""
                rows.append(row)

        return rows

    def parse_all_md_tables(self, text: str) -> List[List[Dict[str, str]]]:
        """Parse all Markdown tables in text."""
        tables = []
        remaining = text
        while True:
            # find next table start
            sep_match = _TABLE_SEP_RE.search(remaining)
            if not sep_match:
                break
            # find header row just before separator
            before = remaining[: sep_match.start()]
            header_lines = [l for l in before.split("\n") if _TABLE_ROW_RE.match(l)]
            if not header_lines:
                remaining = remaining[sep_match.end():]
                continue
            # extract from the header row onwards
            header_start = before.rfind(header_lines[-1])
            table_text = remaining[header_start:]
            table = self.parse_md_table(table_text)
            if table:
                tables.append(table)
            remaining = remaining[sep_match.end() + 200:]  # skip past this table
        return tables

    # ----------------------------------------------------------
    # Number Extraction Helpers
    # ----------------------------------------------------------

    def get_value_from_table(
        self,
        rows: List[Dict[str, str]],
        row_keyword: str,
        col_keyword: str,
        unit_multiplier: float = 1.0,
    ) -> Optional[float]:
        """
        Find row whose first column contains row_keyword,
        then find the column whose header contains col_keyword.
        Returns float value (multiplied by unit_multiplier).
        """
        for row in rows:
            keys = list(row.keys())
            if not keys:
                continue
            first_val = row[keys[0]]
            if row_keyword in first_val:
                for col_name, val in row.items():
                    if col_keyword in col_name:
                        n = _clean_number(val)
                        if n is not None:
                            return n * unit_multiplier
                # if only one data column, return it
                if len(keys) == 2:
                    n = _clean_number(row[keys[1]])
                    if n is not None:
                        return n * unit_multiplier
        return None

    def extract_inline_number(
        self, text: str, pattern: str, group: int = 1, unit_multiplier: float = 1.0
    ) -> Optional[float]:
        """Extract a number from text using a regex pattern."""
        m = re.search(pattern, text)
        if m:
            n = _clean_number(m.group(group))
            if n is not None:
                return n * unit_multiplier
        return None

    # ----------------------------------------------------------
    # Subclass interface
    # ----------------------------------------------------------

    def extract_income_detail(self) -> Dict:
        """Override in subclass."""
        return {}

    def extract_cashflow(self) -> Dict:
        """Override in subclass."""
        return {}

    def run(self, stock_code: str, stock_name: str, report_date: str) -> Dict:
        """
        Run all extractions and return merged result dict ready for upsert.
        """
        result = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_date": report_date,
        }
        result.update(self.extract_income_detail())
        result.update(self.extract_cashflow())
        return result
