# -*- coding: utf-8 -*-
"""
Unit tests for Agent builtin tools.

All external services are mocked - these test the tool wrappers only.
"""
import os
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')

from api.services.agent.schemas import AgentContext


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_ctx(user_id=1, tier="free", role="user"):
    user = MagicMock()
    user.id = user_id
    user.tier = MagicMock(value=tier)
    user.role = MagicMock(value=role)
    return AgentContext(
        user=user,
        db=MagicMock(),
        redis=MagicMock(),
        conversation_id="test-conv",
    )


_PATCH_RUN_SYNC = 'api.services.agent.builtin_tools._run_sync'


class TestQueryPortfolio(unittest.TestCase):
    """T07: query_portfolio tool tests."""

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_with_stocks(self, mock_run):
        mock_run.return_value = [
            {"stock_code": "002594", "stock_name": "BYD", "position_pct": 10.5,
             "profit_27": 5.2, "PE": Decimal("25.3"), "market_cap": 100000},
        ]
        from api.services.agent.builtin_tools import query_portfolio
        result = _run(query_portfolio({}, _make_ctx()))
        self.assertEqual(len(result["stocks"]), 1)
        self.assertEqual(result["stocks"][0]["stock_code"], "002594")
        self.assertEqual(result["total"], 1)

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_empty_portfolio(self, mock_run):
        mock_run.return_value = []
        from api.services.agent.builtin_tools import query_portfolio
        result = _run(query_portfolio({}, _make_ctx()))
        self.assertEqual(result["stocks"], [])

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_service_error(self, mock_run):
        mock_run.side_effect = Exception("DB error")
        from api.services.agent.builtin_tools import query_portfolio
        result = _run(query_portfolio({}, _make_ctx()))
        self.assertIn("error", result)


class TestGetStockIndicators(unittest.TestCase):
    """T08: get_stock_indicators tool tests."""

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_valid_stock(self, mock_run):
        # First call: indicators query, second call: RPS query
        mock_run.side_effect = [
            [("002594", "BYD", 250.0, 248.0, 245.0, 240.0,
              1.5, 1.2, 0.3, 55.0, 1.2, 3.5, 8.0)],
            [(88.5,)],
        ]
        from api.services.agent.builtin_tools import get_stock_indicators
        result = _run(get_stock_indicators({"stock_code": "002594"}, _make_ctx()))
        self.assertEqual(result["stock_code"], "002594")
        self.assertIsNotNone(result["data"])
        self.assertEqual(result["data"]["rps_20"], 88.5)

    def test_invalid_stock_code(self):
        from api.services.agent.builtin_tools import get_stock_indicators
        result = _run(get_stock_indicators({"stock_code": "abc"}, _make_ctx()))
        self.assertIn("error", result)

    def test_empty_stock_code(self):
        from api.services.agent.builtin_tools import get_stock_indicators
        result = _run(get_stock_indicators({"stock_code": ""}, _make_ctx()))
        self.assertIn("error", result)

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_stock_not_found(self, mock_run):
        mock_run.return_value = []
        from api.services.agent.builtin_tools import get_stock_indicators
        result = _run(get_stock_indicators({"stock_code": "999999"}, _make_ctx()))
        self.assertIsNone(result["data"])


class TestSearchKnowledge(unittest.TestCase):
    """T09: search_knowledge tool tests."""

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_search_returns_results(self, mock_run):
        mock_run.return_value = [
            {"content": "Test report content", "metadata": {"source": "report.pdf"},
             "rrf_score": 0.85},
        ]
        from api.services.agent.builtin_tools import search_knowledge
        result = _run(search_knowledge({"query": "test"}, _make_ctx()))
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(result["documents"][0]["source"], "report.pdf")

    def test_empty_query(self):
        from api.services.agent.builtin_tools import search_knowledge
        result = _run(search_knowledge({"query": ""}, _make_ctx()))
        self.assertEqual(result["documents"], [])

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_text_truncation(self, mock_run):
        long_text = "x" * 1000
        mock_run.return_value = [
            {"content": long_text, "metadata": {}, "rrf_score": 0.5},
        ]
        from api.services.agent.builtin_tools import search_knowledge
        result = _run(search_knowledge({"query": "test"}, _make_ctx()))
        self.assertLessEqual(len(result["documents"][0]["text_snippet"]), 504)

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_top_k_param(self, mock_run):
        mock_run.return_value = [
            {"content": f"doc {i}", "metadata": {}, "rrf_score": 0.5}
            for i in range(10)
        ]
        from api.services.agent.builtin_tools import search_knowledge
        result = _run(search_knowledge({"query": "test", "top_k": 3}, _make_ctx()))
        self.assertEqual(len(result["documents"]), 3)


class TestQueryDatabase(unittest.TestCase):
    """T10: query_database tool tests."""

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_normal_query(self, mock_run):
        mock_run.side_effect = [
            {"sql": "SELECT * FROM stocks WHERE pe < 20", "description": "low PE stocks"},
            [{"stock_code": "000858", "pe": 15.0}],
        ]
        from api.services.agent.builtin_tools import query_database
        result = _run(query_database({"query": "PE < 20 stocks"}, _make_ctx()))
        self.assertIn("results", result)

    def test_empty_query(self):
        from api.services.agent.builtin_tools import query_database
        result = _run(query_database({"query": ""}, _make_ctx()))
        self.assertIn("error", result)


class TestGetFearIndex(unittest.TestCase):
    """T11: get_fear_index tool tests."""

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_returns_index(self, mock_run):
        from datetime import datetime
        mock_result = MagicMock()
        mock_result.vix = 18.5
        mock_result.ovx = 30.0
        mock_result.gvz = 15.0
        mock_result.us10y = 4.2
        mock_result.fear_greed_score = 45
        mock_result.market_regime = "neutral"
        mock_result.vix_level = "normal"
        mock_result.risk_alert = None
        mock_result.timestamp = datetime(2026, 4, 18)
        mock_run.return_value = mock_result

        from api.services.agent.builtin_tools import get_fear_index
        result = _run(get_fear_index({}, _make_ctx()))
        self.assertEqual(result["vix"], 18.5)
        self.assertEqual(result["market_regime"], "neutral")

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_service_error(self, mock_run):
        mock_run.side_effect = Exception("service unavailable")
        from api.services.agent.builtin_tools import get_fear_index
        result = _run(get_fear_index({}, _make_ctx()))
        self.assertIn("error", result)


class TestSearchNews(unittest.TestCase):
    """T12: search_news tool tests."""

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_search_by_stock(self, mock_run):
        item = MagicMock()
        item.title = "BYD News"
        item.source = "sina"
        item.publish_time = "2026-04-18"
        item.content = "content here"
        mock_run.return_value = [item]

        from api.services.agent.builtin_tools import search_news
        result = _run(search_news({"query": "BYD", "stock_code": "002594"}, _make_ctx()))
        self.assertEqual(len(result["news"]), 1)
        self.assertEqual(result["news"][0]["title"], "BYD News")

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_empty_results(self, mock_run):
        mock_run.return_value = []
        from api.services.agent.builtin_tools import search_news
        result = _run(search_news({"query": "noresults"}, _make_ctx()))
        self.assertEqual(result["news"], [])


class TestGetHotSectors(unittest.TestCase):
    """T12: get_hot_sectors tool tests."""

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_returns_sectors(self, mock_run):
        mock_run.return_value = [
            ("Electronics", 3.5, 8.2, 1.5, 1),
            ("Banking", -0.5, 2.1, 0.8, 15),
        ]
        from api.services.agent.builtin_tools import get_hot_sectors
        result = _run(get_hot_sectors({}, _make_ctx()))
        self.assertEqual(len(result["sectors"]), 2)
        self.assertEqual(result["sectors"][0]["name"], "Electronics")

    @patch(_PATCH_RUN_SYNC, new_callable=AsyncMock)
    def test_no_data(self, mock_run):
        mock_run.return_value = []
        from api.services.agent.builtin_tools import get_hot_sectors
        result = _run(get_hot_sectors({}, _make_ctx()))
        self.assertEqual(result["sectors"], [])


class TestActionTools(unittest.TestCase):
    """T13: add_watchlist and add_position tool tests."""

    def test_add_watchlist_missing_params(self):
        from api.services.agent.builtin_tools import add_watchlist
        result = _run(add_watchlist({"stock_code": ""}, _make_ctx()))
        self.assertFalse(result["success"])

    def test_add_position_missing_params(self):
        from api.services.agent.builtin_tools import add_position
        result = _run(add_position({"stock_code": "002594"}, _make_ctx()))
        self.assertFalse(result["success"])

    def test_add_watchlist_registered_as_action(self):
        from api.services.agent.tool_registry import get_registry
        tool = get_registry().get_tool("add_watchlist")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.category, "action")

    def test_add_position_requires_pro(self):
        from api.services.agent.tool_registry import get_registry
        tool = get_registry().get_tool("add_position")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.requires_tier, "pro")

    def test_all_tools_registered(self):
        """Verify all expected builtin tools are registered."""
        from api.services.agent.tool_registry import get_registry
        reg = get_registry()
        expected = [
            "query_portfolio", "get_stock_indicators", "search_knowledge",
            "query_database", "get_fear_index", "search_news",
            "get_hot_sectors", "add_watchlist", "add_position", "run_tech_scan",
        ]
        for name in expected:
            self.assertIsNotNone(reg.get_tool(name), f"Tool '{name}' not registered")


if __name__ == '__main__':
    unittest.main()
