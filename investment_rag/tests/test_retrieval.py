# -*- coding: utf-8 -*-
"""Unit tests for intent router and Text2SQL."""
import pytest
from investment_rag.retrieval.intent_router import IntentRouter, RouteResult
from investment_rag.retrieval.text2sql import Text2SQL


# ============================================================
# Intent router tests
# ============================================================
class TestIntentRouter:
    def setup_method(self):
        self.router = IntentRouter()

    def test_rag_intent_analytical(self):
        result = self.router.route("煤炭行业2026年前景分析")
        assert result.intent == "rag"
        assert result.collection == "reports"

    def test_rag_intent_research(self):
        result = self.router.route("为什么煤炭价格持续上涨")
        assert result.intent == "rag"

    def test_sql_intent_valuation(self):
        result = self.router.route("PE小于20且PB小于1的股票")
        assert result.intent == "sql"

    def test_sql_intent_financial(self):
        result = self.router.route("贵州茅台2024年毛利率是多少")
        assert result.intent in ("sql", "hybrid")

    def test_hybrid_intent(self):
        result = self.router.route("营收增长大于20%的股票，找相关研报分析")
        assert result.intent == "hybrid"

    def test_macro_collection(self):
        result = self.router.route("央行降息对市场的影响分析")
        assert result.collection == "macro"

    def test_announcements_collection(self):
        result = self.router.route("最新发布的年报公告")
        assert result.collection == "announcements"

    def test_default_collection(self):
        result = self.router.route("some random query about stuff")
        assert result.collection == "reports"

    def test_confidence(self):
        result = self.router.route("煤炭行业分析")
        assert 0 < result.confidence <= 1.0


# ============================================================
# Text2SQL tests
# ============================================================
class TestText2SQL:
    def setup_method(self):
        # No MySQL connection needed for template building tests
        self.t2s = Text2SQL()

    def test_extract_stock_code(self):
        assert self.t2s._extract_stock_code("600519贵州茅台") == "600519"
        assert self.t2s._extract_stock_code("600519") == "600519"
        assert self.t2s._extract_stock_code("600519.SH") == "600519"
        assert self.t2s._extract_stock_code("no code here") is None

    def test_parse_comparison(self):
        result = self.t2s._parse_comparison("PE<20且PB>1")
        assert len(result) == 2
        assert result[0] == ("pe", "<", "20")
        assert result[1] == ("pb", ">", "1")

    def test_parse_comparison_chinese(self):
        result = self.t2s._parse_comparison("市盈率小于30且市净率大于1")
        assert len(result) == 2

    def test_build_screening_query(self):
        query_info = self.t2s.build_query("PE<20且PB>1的股票")
        assert query_info is not None
        assert "pe_ttm" in query_info["sql"]
        assert "pb" in query_info["sql"]
        assert query_info["params"] == (20.0, 1.0)

    def test_build_stock_metric_query(self):
        query_info = self.t2s.build_query("600519的估值指标")
        assert query_info is not None
        assert "600519" in str(query_info["params"])

    def test_build_no_match(self):
        query_info = self.t2s.build_query("煤炭行业分析报告")
        assert query_info is None

    def test_execute_no_match(self):
        # Should not raise, just return empty
        results = self.t2s.execute("no match query")
        assert results == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
