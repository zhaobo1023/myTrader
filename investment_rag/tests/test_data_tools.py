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


# ---------------------------------------------------------------
# Valuation snapshot tests
# ---------------------------------------------------------------

def _make_fake_valuation_rows(n=250, pe=15.0, pb=1.5, dv=2.0):
    """Helper: return n rows of fake trade_stock_daily_basic data."""
    import pandas as pd
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "trade_date": d.date(),
            "pe_ttm": pe + (i % 30) * 0.5,   # slight variation so percentile is meaningful
            "pb": pb + (i % 20) * 0.05,
            "dv_ttm": dv,
        })
    return rows


def test_get_valuation_snapshot_returns_formatted_string():
    tools = _make_tools()
    fake_rows = _make_fake_valuation_rows(250)
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = fake_rows
        result = tools.get_valuation_snapshot("000858")
    assert isinstance(result, str)
    assert "PE" in result
    assert "分位" in result


def test_get_valuation_snapshot_handles_empty_data():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = []
        result = tools.get_valuation_snapshot("000858")
    assert "不足" in result


def test_get_valuation_snapshot_handles_db_exception():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.side_effect = Exception("DB unavailable")
        result = tools.get_valuation_snapshot("000858")
    assert "失败" in result


def test_quantile_label_boundaries():
    from investment_rag.report_engine.data_tools import ReportDataTools
    assert ReportDataTools._quantile_label(5) == "极低估"
    assert ReportDataTools._quantile_label(25) == "低估"
    assert ReportDataTools._quantile_label(50) == "合理"
    assert ReportDataTools._quantile_label(70) == "偏高估"
    assert ReportDataTools._quantile_label(85) == "高估"
    assert ReportDataTools._quantile_label(97) == "极高估"


def test_get_expected_return_context_returns_string():
    tools = _make_tools()
    fake_rows = _make_fake_valuation_rows(250, pe=15.0, dv=2.5)
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = fake_rows
        result = tools.get_expected_return_context("000858", earnings_growth_2yr=0.10)
    assert isinstance(result, str)
    assert "盈利" in result
    assert "2年预期总回报" in result


def test_get_expected_return_context_handles_no_pe_data():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools._execute_query") as mock_q:
        mock_q.return_value = []
        result = tools.get_expected_return_context("000858")
    assert "历史数据不足" in result
