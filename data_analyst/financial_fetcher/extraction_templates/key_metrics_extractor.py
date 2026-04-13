# -*- coding: utf-8 -*-
"""
LLM-driven key metrics extractor for annual reports.

Reads industry-specific config (key_metrics_config.yaml) and uses LLM
to extract structured financial metrics from annual report Markdown text.

Usage:
    extractor = KeyMetricsExtractor(industry="bank")
    metrics = extractor.extract(md_content, stock_code, stock_name, report_date)
    # metrics = {"other_comprehensive_income": -6.9, "other_equity_instruments": 150.0, ...}
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "key_metrics_config.yaml"

# Max chars to send to LLM (avoid exceeding context window)
_MAX_CONTEXT_CHARS = 60000


def _load_industry_config(industry: str) -> Dict:
    """Load metrics config for a specific industry."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        all_cfg = yaml.safe_load(f)
    if industry not in all_cfg:
        raise ValueError(
            f"Industry '{industry}' not found in key_metrics_config.yaml. "
            f"Available: {list(all_cfg.keys())}"
        )
    return all_cfg[industry]


def _build_prompt(metrics_cfg: List[Dict], text_excerpt: str) -> str:
    """Build the LLM extraction prompt."""
    fields_desc = []
    for i, m in enumerate(metrics_cfg, 1):
        aliases = ", ".join(m.get("aliases", []))
        unit_label = {"yi": "亿元", "pct": "%", "count": "个", "ratio": "比率"}.get(
            m["unit"], m["unit"]
        )
        required_tag = " [必须]" if m.get("required") else ""
        fields_desc.append(
            f"{i}. {m['name']} (key: {m['key']}){required_tag}\n"
            f"   单位: {unit_label}\n"
            f"   说明: {m['description']}\n"
            f"   别名: {aliases}"
        )
    fields_text = "\n".join(fields_desc)

    return f"""你是一个财务数据提取专家。请从下面的年报文本中，精准提取以下关键指标的数值。

## 提取要求

1. 只提取合并报表口径的数值（归属于母公司股东的），不要用分部或子公司数据
2. 数值统一转换为指定单位（亿元或百分比）后返回
3. 如果年报中有多个相近的数值（如当期和上期），取当期（最新报告期）的数值
4. 如果某个指标在年报中确实找不到，返回 null
5. 对于负数，直接返回负数（如 -6.9），不要用括号表示

## 需要提取的指标

{fields_text}

## 输出格式

严格返回 JSON 对象，不要包含任何其他文字或 markdown 标记。
格式: {{"key1": 数值或null, "key2": 数值或null, ...}}

例如: {{"other_comprehensive_income": -6.9, "total_comprehensive_income": 250.3, "other_equity_instruments": null}}

## 年报文本

{text_excerpt}"""


def _extract_relevant_sections(md_content: str, metrics_cfg: List[Dict]) -> str:
    """Extract relevant sections from the full annual report text.

    Instead of sending the entire document (which can be very large),
    find sections that are likely to contain the target metrics.
    """
    # Collect all keywords to search for
    keywords = []
    for m in metrics_cfg:
        keywords.append(m["name"])
        keywords.extend(m.get("aliases", []))

    # Find relevant chunks around each keyword occurrence
    chunks = []
    seen_positions = set()
    for kw in keywords:
        for match in re.finditer(re.escape(kw), md_content):
            pos = match.start()
            # Snap to 2000-char blocks to avoid overlapping tiny fragments
            block_start = max(0, pos - 500)
            block_key = block_start // 1000  # dedup by 1000-char blocks
            if block_key not in seen_positions:
                seen_positions.add(block_key)
                chunk = md_content[block_start: pos + 1500]
                chunks.append((block_start, chunk))

    if not chunks:
        # Fallback: use the first N chars
        return md_content[:_MAX_CONTEXT_CHARS]

    # Sort by position and concatenate
    chunks.sort(key=lambda x: x[0])
    result_parts = []
    total_len = 0
    for _, chunk in chunks:
        if total_len + len(chunk) > _MAX_CONTEXT_CHARS:
            break
        result_parts.append(chunk)
        total_len += len(chunk)

    return "\n...\n".join(result_parts)


def _parse_llm_response(response: str, metrics_cfg: List[Dict]) -> Dict[str, Any]:
    """Parse LLM JSON response into a clean metrics dict."""
    # Strip markdown code block if present
    response = response.strip()
    if response.startswith("```"):
        lines = response.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        response = "\n".join(lines)

    # Strip any leading/trailing non-JSON text
    # Find the first { and last }
    first_brace = response.find("{")
    last_brace = response.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        response = response[first_brace: last_brace + 1]

    try:
        raw = json.loads(response)
    except json.JSONDecodeError as e:
        logger.error("[KeyMetrics] Failed to parse LLM response as JSON: %s", e)
        logger.debug("[KeyMetrics] Raw response: %s", response[:500])
        return {}

    # Validate and convert values
    valid_keys = {m["key"] for m in metrics_cfg}
    unit_map = {m["key"]: m["unit"] for m in metrics_cfg}
    result = {}
    for key, val in raw.items():
        if key not in valid_keys:
            continue
        if val is None:
            result[key] = None
            continue
        try:
            val = float(val)
            result[key] = val
        except (ValueError, TypeError):
            logger.warning("[KeyMetrics] Invalid value for %s: %s", key, val)
            result[key] = None

    # Log missing required fields
    for m in metrics_cfg:
        if m.get("required") and m["key"] not in result:
            logger.warning("[KeyMetrics] Required metric '%s' not found in LLM response", m["name"])

    return result


class KeyMetricsExtractor:
    """Industry-configurable key metrics extractor using LLM."""

    def __init__(self, industry: str = "bank", llm_client=None):
        """
        Args:
            industry: Industry key matching key_metrics_config.yaml
            llm_client: Optional LLMClient instance. If None, creates one.
        """
        self.industry = industry
        self._cfg = _load_industry_config(industry)
        self._metrics = self._cfg["metrics"]
        self._llm = llm_client

    def _get_llm(self):
        if self._llm is None:
            from investment_rag.embeddings.embed_model import LLMClient
            self._llm = LLMClient()
        return self._llm

    @property
    def metric_keys(self) -> List[str]:
        """Return all metric keys for this industry."""
        return [m["key"] for m in self._metrics]

    @property
    def target_tables(self) -> Dict[str, List[str]]:
        """Return {table_name: [field_keys]} mapping."""
        tables = {}
        for m in self._metrics:
            table = m["table"]
            if table not in tables:
                tables[table] = []
            tables[table].append(m["key"])
        return tables

    def extract(
        self,
        md_content: str,
        stock_code: str,
        stock_name: str,
        report_date: str,
    ) -> Dict[str, Any]:
        """Extract key metrics from annual report text using LLM.

        Args:
            md_content: Full annual report in Markdown format.
            stock_code: e.g. "600015"
            stock_name: e.g. "华夏银行"
            report_date: e.g. "2025-12-31"

        Returns:
            Dict with metric keys as fields, grouped by target table:
            {
                "financial_income_detail": {
                    "stock_code": "600015",
                    "stock_name": "华夏银行",
                    "report_date": "2025-12-31",
                    "other_comprehensive_income": -6.9,
                    ...
                },
                "_raw": {  # flat dict of all extracted values
                    "other_comprehensive_income": -6.9,
                    ...
                }
            }
        """
        logger.info(
            "[KeyMetrics] Extracting %d metrics for %s(%s) %s, industry=%s",
            len(self._metrics), stock_name, stock_code, report_date, self.industry,
        )

        # Step 1: Extract relevant sections
        excerpt = _extract_relevant_sections(md_content, self._metrics)
        logger.info("[KeyMetrics] Excerpt length: %d chars (from %d total)",
                     len(excerpt), len(md_content))

        # Step 2: Build prompt and call LLM
        prompt = _build_prompt(self._metrics, excerpt)
        llm = self._get_llm()
        response = llm.generate(
            prompt=prompt,
            system_prompt="你是财务报表数据提取专家，只返回JSON，不做分析。",
            temperature=0.1,
            max_tokens=1024,
        )

        # Step 3: Parse response
        raw_metrics = _parse_llm_response(response, self._metrics)

        # Step 4: Group by target table
        base_fields = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_date": report_date,
        }
        result = {"_raw": dict(raw_metrics)}

        for table, keys in self.target_tables.items():
            table_data = dict(base_fields)
            has_data = False
            for k in keys:
                if k in raw_metrics and raw_metrics[k] is not None:
                    table_data[k] = raw_metrics[k]
                    has_data = True
            if has_data:
                table_data["source"] = "llm_extraction"
                result[table] = table_data

        # Log summary
        extracted = sum(1 for v in raw_metrics.values() if v is not None)
        total = len(self._metrics)
        logger.info("[KeyMetrics] Extracted %d/%d metrics: %s", extracted, total, raw_metrics)

        return result

    @staticmethod
    def list_industries() -> List[str]:
        """List all configured industries."""
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return list(yaml.safe_load(f).keys())
