# -*- coding: utf-8 -*-
"""
Unit tests for Agent core data structures: ToolDef, AgentContext, ToolCallResult.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')


class TestToolDef(unittest.TestCase):
    """Tests for ToolDef dataclass."""

    def _make_tool_def(self, **overrides):
        from api.services.agent.schemas import ToolDef
        defaults = {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "source": "builtin",
            "handler": AsyncMock(return_value={"ok": True}),
        }
        defaults.update(overrides)
        return ToolDef(**defaults)

    def test_construction_defaults(self):
        tool = self._make_tool_def()
        self.assertEqual(tool.requires_tier, "free")
        self.assertEqual(tool.category, "data")
        self.assertEqual(tool.source, "builtin")

    def test_construction_with_overrides(self):
        tool = self._make_tool_def(requires_tier="pro", category="action")
        self.assertEqual(tool.requires_tier, "pro")
        self.assertEqual(tool.category, "action")

    def test_to_openai_tool(self):
        tool = self._make_tool_def(name="query_portfolio", description="Query user portfolio")
        result = tool.to_openai_tool()
        self.assertEqual(result["type"], "function")
        self.assertEqual(result["function"]["name"], "query_portfolio")
        self.assertEqual(result["function"]["description"], "Query user portfolio")
        self.assertIn("parameters", result["function"])

    def test_to_info_dict(self):
        tool = self._make_tool_def(name="my_tool", source="plugin", category="analysis")
        info = tool.to_info_dict()
        self.assertEqual(info["name"], "my_tool")
        self.assertEqual(info["source"], "plugin")
        self.assertEqual(info["category"], "analysis")
        self.assertNotIn("handler", info)


class TestAgentContext(unittest.TestCase):
    """Tests for AgentContext dataclass."""

    def test_construction(self):
        from api.services.agent.schemas import AgentContext
        ctx = AgentContext(
            user=MagicMock(),
            db=MagicMock(),
            redis=MagicMock(),
            conversation_id="conv-123",
        )
        self.assertEqual(ctx.conversation_id, "conv-123")
        self.assertEqual(ctx.page_context, {})

    def test_page_context_custom(self):
        from api.services.agent.schemas import AgentContext
        ctx = AgentContext(
            user=MagicMock(),
            db=MagicMock(),
            redis=MagicMock(),
            conversation_id="conv-456",
            page_context={"page": "market", "stock_code": "002594"},
        )
        self.assertEqual(ctx.page_context["page"], "market")
        self.assertEqual(ctx.page_context["stock_code"], "002594")


class TestToolCallResult(unittest.TestCase):
    """Tests for ToolCallResult dataclass."""

    def test_defaults(self):
        from api.services.agent.schemas import ToolCallResult
        r = ToolCallResult(name="test", result={"data": 1}, call_id="c1")
        self.assertTrue(r.success)
        self.assertEqual(r.error, "")
        self.assertEqual(r.duration_ms, 0.0)

    def test_error_result(self):
        from api.services.agent.schemas import ToolCallResult
        r = ToolCallResult(
            name="test", result={}, call_id="c2",
            success=False, error="timeout",
        )
        self.assertFalse(r.success)
        self.assertEqual(r.error, "timeout")


class TestToolCallTimer(unittest.TestCase):
    """Tests for ToolCallTimer context manager."""

    def test_timing(self):
        import time
        from api.services.agent.schemas import ToolCallTimer
        with ToolCallTimer() as t:
            time.sleep(0.01)
        self.assertGreater(t.duration_ms, 5)


if __name__ == '__main__':
    unittest.main()
