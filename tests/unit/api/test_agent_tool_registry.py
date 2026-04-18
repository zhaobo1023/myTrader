# -*- coding: utf-8 -*-
"""
Unit tests for ToolRegistry - registration, filtering, execution.
"""
import os
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')

from api.services.agent.schemas import ToolDef, AgentContext


def _make_tool(name="tool1", requires_tier="free", category="data", source="builtin"):
    return ToolDef(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}, "required": []},
        source=source,
        handler=AsyncMock(return_value={"result": name}),
        requires_tier=requires_tier,
        category=category,
    )


def _make_user(tier="free", role="user"):
    user = MagicMock()
    user.tier = MagicMock(value=tier)
    user.role = MagicMock(value=role)
    return user


def _make_context():
    return AgentContext(
        user=_make_user(),
        db=MagicMock(),
        redis=MagicMock(),
        conversation_id="conv-test",
    )


class TestToolRegistry(unittest.TestCase):
    """Tests for ToolRegistry core operations."""

    def _make_registry(self):
        from api.services.agent.tool_registry import ToolRegistry
        return ToolRegistry()

    def test_register_builtin(self):
        reg = self._make_registry()
        tool = _make_tool("my_tool")
        reg.register_builtin(tool)
        self.assertEqual(tool.source, "builtin")
        self.assertIsNotNone(reg.get_tool("my_tool"))

    def test_register_duplicate_raises(self):
        reg = self._make_registry()
        reg.register(_make_tool("dup"))
        with self.assertRaises(ValueError):
            reg.register(_make_tool("dup"))

    def test_register_plugin(self):
        reg = self._make_registry()
        tool = _make_tool("plugin_tool", source="builtin")
        reg.register_plugin(tool)
        self.assertEqual(tool.source, "plugin")

    def test_register_mcp(self):
        reg = self._make_registry()
        tool = _make_tool("mcp_tool", source="builtin")
        reg.register_mcp(tool)
        self.assertEqual(tool.source, "mcp")

    def test_get_tool_not_found(self):
        reg = self._make_registry()
        self.assertIsNone(reg.get_tool("nonexistent"))

    def test_unregister(self):
        reg = self._make_registry()
        reg.register(_make_tool("removable"))
        reg.unregister("removable")
        self.assertIsNone(reg.get_tool("removable"))

    def test_unregister_nonexistent_no_error(self):
        reg = self._make_registry()
        reg.unregister("nope")  # should not raise

    def test_get_all_tools(self):
        reg = self._make_registry()
        reg.register(_make_tool("a"))
        reg.register(_make_tool("b"))
        self.assertEqual(len(reg.get_all_tools()), 2)


class TestToolRegistryFiltering(unittest.TestCase):
    """Tests for tier-based tool filtering."""

    def _make_registry_with_tools(self):
        from api.services.agent.tool_registry import ToolRegistry
        reg = ToolRegistry()
        reg.register(_make_tool("free_tool", requires_tier="free"))
        reg.register(_make_tool("pro_tool", requires_tier="pro"))
        return reg

    def test_free_user_sees_only_free(self):
        reg = self._make_registry_with_tools()
        user = _make_user(tier="free", role="user")
        tools = reg.get_tools_for_user(user)
        names = [t.name for t in tools]
        self.assertIn("free_tool", names)
        self.assertNotIn("pro_tool", names)

    def test_pro_user_sees_all(self):
        reg = self._make_registry_with_tools()
        user = _make_user(tier="pro", role="user")
        tools = reg.get_tools_for_user(user)
        self.assertEqual(len(tools), 2)

    def test_admin_user_sees_all(self):
        reg = self._make_registry_with_tools()
        user = _make_user(tier="free", role="admin")
        tools = reg.get_tools_for_user(user)
        self.assertEqual(len(tools), 2)

    def test_get_openai_tools_format(self):
        reg = self._make_registry_with_tools()
        user = _make_user(tier="pro")
        openai_tools = reg.get_openai_tools(user)
        self.assertEqual(len(openai_tools), 2)
        for t in openai_tools:
            self.assertEqual(t["type"], "function")
            self.assertIn("name", t["function"])
            self.assertIn("description", t["function"])
            self.assertIn("parameters", t["function"])


class TestToolRegistryExecution(unittest.TestCase):
    """Tests for tool execution."""

    def test_execute_success(self):
        from api.services.agent.tool_registry import ToolRegistry
        reg = ToolRegistry()
        handler = AsyncMock(return_value={"data": "ok"})
        reg.register(_make_tool("exec_tool"))
        reg.get_tool("exec_tool").handler = handler

        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            reg.execute("exec_tool", {"arg": 1}, ctx)
        )
        self.assertTrue(result.success)
        self.assertEqual(result.result, {"data": "ok"})
        self.assertGreaterEqual(result.duration_ms, 0)
        handler.assert_called_once_with({"arg": 1}, ctx)

    def test_execute_not_found(self):
        from api.services.agent.tool_registry import ToolRegistry
        reg = ToolRegistry()
        ctx = _make_context()
        with self.assertRaises(KeyError):
            asyncio.get_event_loop().run_until_complete(
                reg.execute("nonexistent", {}, ctx)
            )

    def test_execute_handler_error(self):
        from api.services.agent.tool_registry import ToolRegistry
        reg = ToolRegistry()
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        tool = _make_tool("fail_tool")
        tool.handler = handler
        reg.register(tool)

        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            reg.execute("fail_tool", {}, ctx)
        )
        self.assertFalse(result.success)
        self.assertIn("boom", result.error)
        self.assertEqual(result.result, {})

    def test_execute_includes_duration(self):
        from api.services.agent.tool_registry import ToolRegistry
        reg = ToolRegistry()

        async def slow_handler(params, ctx):
            import asyncio as aio
            await aio.sleep(0.01)
            return {"ok": True}

        tool = _make_tool("slow_tool")
        tool.handler = slow_handler
        reg.register(tool)

        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            reg.execute("slow_tool", {}, ctx)
        )
        self.assertTrue(result.success)
        self.assertGreater(result.duration_ms, 5)


class TestBuiltinToolDecorator(unittest.TestCase):
    """Tests for @builtin_tool decorator."""

    def test_decorator_registers_tool(self):
        from api.services.agent.tool_registry import get_registry, builtin_tool

        @builtin_tool(
            name="_test_decorator_tool",
            description="Test tool via decorator",
            parameters={"type": "object", "properties": {}, "required": []},
            category="data",
            requires_tier="free",
        )
        async def _test_decorator_tool(params, ctx):
            return {"decorated": True}

        reg = get_registry()
        tool = reg.get_tool("_test_decorator_tool")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.source, "builtin")
        self.assertEqual(tool.category, "data")
        # Cleanup
        reg.unregister("_test_decorator_tool")


if __name__ == '__main__':
    unittest.main()
