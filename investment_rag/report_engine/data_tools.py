# -*- coding: utf-8 -*-
"""
ReportDataTools - Unified data collection layer for report generation.

Integrates three data sources:
1. RAG:       ChromaDB vector search + BM25 + Reranker (existing investment_rag/retrieval/)
2. Financial: AKShare financial summary (investment_rag/ingest/loaders/)
3. Technical: K-line + indicators + signals (strategist/tech_scan/)

DESIGN RULES:
- Technical K-line data MUST go through DataFetcher (not raw SQL). DataFetcher handles
  column name mapping (open_price -> open etc.) and ETF vs stock table routing.
- SignalLevel.name (RED/YELLOW/GREEN/INFO) is used instead of .value to avoid emoji.
- All methods return plain formatted strings for direct Prompt embedding.
"""
import logging
from typing import List, Optional

import pandas as pd

# DataFetcher is imported at module level so that tests can patch
# "investment_rag.report_engine.data_tools.DataFetcher".
# The import is guarded so the module stays importable even if
# strategist.tech_scan is not on the path.
try:
    from strategist.tech_scan.data_fetcher import DataFetcher
except ImportError:
    DataFetcher = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class ReportDataTools:
    """Unified data collection tools for research report generation."""

    def __init__(self, db_env: str = "online"):
        # Lazy imports to avoid mandatory heavy dependencies at module import time.
        # Tests use __new__ + manual attribute injection, bypassing __init__.
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        from investment_rag.retrieval.reranker import Reranker
        from investment_rag.ingest.loaders.akshare_loader import AKShareLoader

        self._db_env = db_env
        self._retriever = HybridRetriever()
        self._reranker = Reranker()
        self._financial_loader = AKShareLoader()

    # ----------------------------------------------------------
    # 1. RAG Retrieval
    # ----------------------------------------------------------

    def query_rag(
        self,
        query: str,
        stock_code: Optional[str] = None,
        collection: str = "reports",
        top_k: int = 5,
    ) -> str:
        """
        Retrieve relevant document chunks via HybridRetriever + Reranker.

        Args:
            query: Search query
            stock_code: If specified, filter ChromaDB by stock_code metadata
            collection: ChromaDB collection name (reports/announcements/notes/macro)
            top_k: Final number of results

        Returns:
            Formatted text with source annotations
        """
        where = {"stock_code": stock_code} if stock_code else None

        try:
            hits = self._retriever.retrieve(
                query=query,
                collection=collection,
                top_k=top_k * 2,
                where=where,
            )
            hits = self._reranker.rerank(query, hits, top_k=top_k)
        except Exception as e:
            logger.warning("[ReportDataTools] RAG retrieve failed: %s", e)
            return "[RAG retrieval failed, skipping]"

        if not hits:
            return "[RAG: no relevant content found]"

        parts = []
        for i, h in enumerate(hits, 1):
            source = h.get("metadata", {}).get("source", "unknown source")
            text = h.get("text", "")[:600]
            parts.append(f"[Source {i}: {source}]\n{text}")

        return "\n\n".join(parts)

    def query_rag_multi(
        self,
        queries: List[str],
        stock_name: str,
        stock_code: Optional[str] = None,
        collection: str = "reports",
        top_k_per_query: int = 3,
    ) -> str:
        """
        Multi-query retrieval with deduplication and merge.

        Args:
            queries: Query template list (supports {stock_name} placeholder)
            stock_name: Company name for template substitution
            stock_code: Optional stock filter
            collection: Collection name
            top_k_per_query: Results per query

        Returns:
            Deduplicated merged text
        """
        seen_ids: set = set()
        all_hits: list = []
        where = {"stock_code": stock_code} if stock_code else None

        for q_tpl in queries:
            q = q_tpl.format(stock_name=stock_name)
            try:
                hits = self._retriever.retrieve(
                    query=q,
                    collection=collection,
                    top_k=top_k_per_query * 2,
                    where=where,
                )
                hits = self._reranker.rerank(q, hits, top_k=top_k_per_query)
            except Exception as e:
                logger.warning("[ReportDataTools] multi-query failed '%s': %s", q, e)
                continue

            for h in hits:
                uid = h.get("id") or h.get("text", "")[:80]
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    all_hits.append(h)

        if not all_hits:
            return "[RAG multi-query: no relevant content found]"

        parts = []
        limit = top_k_per_query * len(queries)
        for i, h in enumerate(all_hits[:limit], 1):
            source = h.get("metadata", {}).get("source", "unknown source")
            text = h.get("text", "")[:500]
            parts.append(f"[Source {i}: {source}]\n{text}")

        return "\n\n".join(parts)

    # ----------------------------------------------------------
    # 2. Financial Data
    # ----------------------------------------------------------

    def get_financial_data(self, stock_code: str, years: int = 3) -> str:
        """
        Get AKShare financial summary, return formatted text.

        Args:
            stock_code: Stock code (numeric, e.g. "000858")
            years: Number of years

        Returns:
            Formatted financial summary text
        """
        clean_code = stock_code.split(".")[0]
        result = self._financial_loader.get_financial_data(clean_code, years)
        if result.get("error"):
            logger.warning("[ReportDataTools] Financial data error: %s", result["error"])
        summary = result.get("summary", "")
        return summary if summary else f"[Financial Data] {clean_code} no data available"

    # ----------------------------------------------------------
    # 3. Technical Analysis
    # ----------------------------------------------------------

    def get_tech_analysis(self, stock_code: str, lookback_days: int = 120) -> str:
        """
        Load K-line via DataFetcher, compute indicators with IndicatorCalculator,
        detect signals with SignalDetector, return formatted text for LLM.

        Uses DataFetcher (not raw SQL) because:
        - DataFetcher correctly maps open_price/high_price/low_price/close_price column names
        - DataFetcher handles ETF (trade_etf_daily) vs stock (trade_stock_daily) routing

        Args:
            stock_code: Stock code (with or without suffix)
            lookback_days: Calendar days to look back

        Returns:
            Formatted technical analysis text
        """
        try:
            from strategist.tech_scan.indicator_calculator import IndicatorCalculator
            from strategist.tech_scan.signal_detector import SignalDetector
        except ImportError as e:
            logger.error("[ReportDataTools] tech_scan import failed: %s", e)
            return f"[Technical] tech_scan import failed: {e}"

        if DataFetcher is None:
            return "[Technical] DataFetcher not available (strategist.tech_scan not installed)"

        fetcher = DataFetcher(env=self._db_env)
        try:
            df = fetcher.fetch_daily_data([stock_code], lookback_days=lookback_days)
        except Exception as e:
            logger.warning("[ReportDataTools] DataFetcher failed for %s: %s", stock_code, e)
            return f"[Technical] {stock_code} data fetch failed: {e}"

        if df is None or df.empty:
            return f"[Technical] {stock_code} no K-line data available"

        try:
            calc = IndicatorCalculator()
            df = calc.calculate_all(df)
            latest = df.iloc[-1]
            detector = SignalDetector()
            signals = detector.detect_all(latest)
            kdj_signals = detector.detect_kdj_signals(latest)
            all_signals = signals + kdj_signals
            trend = detector.get_trend_status(latest)
            macd_div = detector.detect_macd_divergence(df)
        except Exception as e:
            logger.warning("[ReportDataTools] Indicator calculation failed: %s", e)
            return f"[Technical] {stock_code} indicator calculation failed: {e}"

        return self._format_tech_text(latest, all_signals, trend, macd_div)

    def _format_tech_text(
        self,
        latest: pd.Series,
        signals: list,
        trend: str,
        macd_divergence: dict,
    ) -> str:
        """Format technical indicators as LLM-readable plain text. No emoji."""

        def _v(val, fmt=".2f"):
            if val is None:
                return "N/A"
            try:
                f = float(val)
                if f != f:  # NaN check
                    return "N/A"
                return f"{f:{fmt}}"
            except (TypeError, ValueError):
                return "N/A"

        lines = [
            f"[Technical Indicators] Latest date: {latest.get('trade_date', 'N/A')}",
            f"Close: {_v(latest.get('close'))}",
            f"MA5/20/60/250: {_v(latest.get('ma5'))}/{_v(latest.get('ma20'))}/{_v(latest.get('ma60'))}/{_v(latest.get('ma250'))}",
            f"MACD DIF/DEA: {_v(latest.get('macd_dif'), '.4f')}/{_v(latest.get('macd_dea'), '.4f')}",
            f"RSI(14): {_v(latest.get('rsi'), '.1f')}",
            f"KDJ K/D/J: {_v(latest.get('kdj_k'), '.1f')}/{_v(latest.get('kdj_d'), '.1f')}/{_v(latest.get('kdj_j'), '.1f')}",
            f"BOLL Upper/Middle/Lower: {_v(latest.get('boll_upper'))}/{_v(latest.get('boll_middle'))}/{_v(latest.get('boll_lower'))}",
            f"ATR(14): {_v(latest.get('atr_14'))}",
            f"Volume Ratio (5-day): {_v(latest.get('volume_ratio'), '.2f')}",
            f"Trend: {trend}",
            f"MACD Divergence: {macd_divergence.get('type', 'None')} "
            f"(confidence={macd_divergence.get('confidence', 'N/A')}, "
            f"{macd_divergence.get('description', '')})",
            "",
            "[Signal List]",
        ]

        if not signals:
            lines.append("  (no signals triggered)")
        else:
            for sig in signals:
                # Use .name (RED/YELLOW/GREEN/INFO) NOT .value (has emoji)
                level_tag = f"[{sig.level.name}]"
                lines.append(f"  {level_tag} {sig.name}: {sig.description}")

        return "\n".join(lines)
