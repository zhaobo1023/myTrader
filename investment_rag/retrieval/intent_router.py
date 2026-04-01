# -*- coding: utf-8 -*-
"""
Intent router: rule-based query classification.

Routes queries to:
    - "rag"      -> Hybrid RAG retrieval
    - "sql"      -> Text2SQL structured query
    - "hybrid"   -> SQL first, then RAG with SQL results as context
"""
import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    """Result of intent routing."""
    intent: str          # "rag", "sql", or "hybrid"
    collection: str      # target collection for RAG
    sql_template: Optional[str] = None
    extracted_params: Optional[dict] = None
    confidence: float = 0.0


# Patterns that indicate structured data queries
SQL_PATTERNS = [
    # Financial metrics
    r'(毛利率|净利率|营收|净利润|ROE|ROA|资产负债率|现金流)',
    # Valuation metrics
    r'(市盈率|PE|市净率|PB|市销率|PS|市值|估值)',
    # Factor screening
    r'(PE\s*[<>=]|PB\s*[<>=]|市值\s*[<>=]|换手率\s*[<>=])',
    # Specific stock queries with numbers
    r'(\d{4}年|\d{1,2}月).*(财报|业绩|利润|收入)',
    r'(涨幅|跌幅|涨跌|收益率)\s*[>>=<]\s*\d+',
    # Ranking queries
    r'(排名|前\d+|TOP\d+|top\d+).*?(股|行业|板块)',
]

# Patterns that suggest RAG (semantic/analytical) queries
RAG_PATTERNS = [
    r'(分析|研究|报告|策略|观点|前景|趋势)',
    r'(为什么|原因|逻辑|影响|怎么看)',
    r'(行业|板块|赛道).*?(机会|风险|展望)',
    r'(研报|券商|分析师)',
]

# Patterns for hybrid queries (need both SQL and RAG)
HYBRID_PATTERNS = [
    r'(增长|增速|同比|环比).{0,5}?\d+%.*?(研报|报告|分析)',
    r'(财报|业绩).*?(分析|解读|点评)',
    r'(行业|板块).{0,5}?(筛选|筛选出).{0,5}?(条件|指标)',
    r'(营收|利润|收入).{0,10}?(研报|报告|分析|点评)',
]


def _match_patterns(text: str, patterns: list) -> int:
    """Count how many patterns match the text."""
    count = 0
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            count += 1
    return count


def _extract_collection(text: str) -> str:
    """Guess the target collection from query text."""
    text_lower = text.lower()

    # Check for specific sectors/keywords
    sector_keywords = {
        "announcements": ["公告", "年报", "季报", "半年报", "财报披露"],
        "notes": ["笔记", "个人", "持仓", "观察"],
        "macro": ["宏观", "政策", "央行", "利率", "通胀", "CPI", "PPI",
                   "PMI", "GDP", "社融", "M2"],
    }

    for collection, keywords in sector_keywords.items():
        for kw in keywords:
            if kw in text_lower:
                return collection

    return "reports"


class IntentRouter:
    """Rule-based query intent router."""

    def route(self, query: str) -> RouteResult:
        """Classify query intent.

        Args:
            query: User query string.

        Returns:
            RouteResult with intent, collection, and optional SQL info.
        """
        query = query.strip()

        # Count pattern matches
        sql_score = _match_patterns(query, SQL_PATTERNS)
        rag_score = _match_patterns(query, RAG_PATTERNS)
        hybrid_score = _match_patterns(query, HYBRID_PATTERNS)

        # Determine intent
        if hybrid_score > 0 and (sql_score > 0 or rag_score > 0):
            intent = "hybrid"
            confidence = min(0.9, 0.5 + hybrid_score * 0.15)
        elif sql_score > rag_score and sql_score > 0:
            intent = "sql"
            confidence = min(0.9, 0.5 + sql_score * 0.15)
        else:
            intent = "rag"
            confidence = min(0.9, 0.5 + rag_score * 0.15 + sql_score * 0.05)

        collection = _extract_collection(query)

        return RouteResult(
            intent=intent,
            collection=collection,
            confidence=confidence,
        )
