# -*- coding: utf-8 -*-
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


def _make_tools():
    """Create ReportDataTools with all external calls mocked out."""
    from investment_rag.report_engine.data_tools import ReportDataTools
    tools = ReportDataTools.__new__(ReportDataTools)
    tools._db_env = "online"
    tools._retriever = MagicMock()
    tools._reranker = MagicMock()
    tools._financial_loader = MagicMock()
    return tools


def test_query_rag_returns_formatted_string():
    tools = _make_tools()
    tools._retriever.retrieve.return_value = [
        {"id": "d1", "text": "Revenue grew 30%", "metadata": {"source": "report.pdf"}, "rrf_score": 0.8}
    ]
    tools._reranker.rerank.return_value = tools._retriever.retrieve.return_value
    result = tools.query_rag("revenue growth", stock_code="300750", top_k=3)
    assert isinstance(result, str)
    assert len(result) > 0


def test_query_rag_handles_empty_results():
    tools = _make_tools()
    tools._retriever.retrieve.return_value = []
    tools._reranker.rerank.return_value = []
    result = tools.query_rag("revenue growth", stock_code="300750")
    assert isinstance(result, str)


def test_query_rag_handles_retrieval_exception():
    tools = _make_tools()
    tools._retriever.retrieve.side_effect = Exception("ChromaDB unavailable")
    result = tools.query_rag("revenue growth", stock_code="300750")
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_financial_data_returns_string():
    tools = _make_tools()
    tools._financial_loader.get_financial_data.return_value = {
        "raw": {},
        "summary": "[Financial Summary] 000858 Period 1: ROE=25.3",
        "error": None,
    }
    result = tools.get_financial_data("000858", years=2)
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_tech_analysis_handles_empty_df():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools.DataFetcher") as mock_cls:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_daily_data.return_value = pd.DataFrame()
        mock_cls.return_value = mock_fetcher
        result = tools.get_tech_analysis("000858")
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_tech_analysis_returns_formatted_text():
    tools = _make_tools()
    # Build a minimal dataframe that IndicatorCalculator can process
    mock_df = pd.DataFrame([{
        "stock_code": "000858",
        "trade_date": pd.Timestamp("2026-04-01"),
        "open": 150.0, "high": 155.0, "low": 148.0, "close": 152.0, "volume": 1e7,
    }] * 30)

    with patch("investment_rag.report_engine.data_tools.DataFetcher") as mock_cls:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_daily_data.return_value = mock_df
        mock_cls.return_value = mock_fetcher
        result = tools.get_tech_analysis("000858")

    assert isinstance(result, str)
    assert len(result) > 50
    # Must NOT contain emoji characters
    for char in result:
        code_point = ord(char)
        assert code_point < 0x1F600 or code_point > 0x1FFFF, f"Emoji found: {char!r}"


def test_query_rag_multi_deduplicates():
    tools = _make_tools()
    hit = {"id": "d1", "text": "Revenue grew 30%", "metadata": {"source": "r.pdf"}, "rrf_score": 0.8}
    tools._retriever.retrieve.return_value = [hit]
    tools._reranker.rerank.return_value = [hit]
    result = tools.query_rag_multi(
        queries=["{stock_name} revenue", "{stock_name} profit"],
        stock_name="Wuliangye",
        top_k_per_query=2,
    )
    assert isinstance(result, str)
    # Same doc returned by both queries, should appear only once in result
    assert result.count("Revenue grew 30%") == 1
