# -*- coding: utf-8 -*-
"""
Unit tests for MCP Client (T35), ToolRegistry MCP integration (T37),
MCP API schemas (T36), and MCP e2e flow (T38).
"""
from __future__ import annotations

import asyncio
import pytest
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.agent.mcp_client import MCPServerConfig, MCPToolSource
from api.services.agent.schemas import AgentContext, ToolDef
from api.services.agent.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers: fake MCP objects
# ---------------------------------------------------------------------------

@dataclass
class FakeMCPTool:
    name: str = "get_price"
    description: str = "Get stock price"
    inputSchema: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {"symbol": {"type": "string"}},
        "required": ["symbol"],
    })


@dataclass
class FakeToolResult:
    content: list = field(default_factory=list)
    isError: bool = False


@dataclass
class FakeTextContent:
    text: str = '{"price": 100.5}'


@dataclass
class FakeListToolsResult:
    tools: list = field(default_factory=list)


class FakeSession:
    """Mock MCP ClientSession."""
    def __init__(self, tools=None, call_result=None):
        self._tools = tools or []
        self._call_result = call_result or FakeToolResult(content=[FakeTextContent()])

    async def initialize(self):
        pass

    async def list_tools(self):
        return FakeListToolsResult(tools=self._tools)

    async def call_tool(self, name, arguments=None):
        return self._call_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# T35: MCPToolSource unit tests
# ---------------------------------------------------------------------------

class TestMCPServerConfig:
    def test_stdio_config(self):
        c = MCPServerConfig(name="test", transport="stdio", command="echo", args=["hello"])
        assert c.name == "test"
        assert c.transport == "stdio"
        assert c.command == "echo"

    def test_sse_config(self):
        c = MCPServerConfig(name="test-sse", transport="sse", url="http://localhost:3001/mcp")
        assert c.url == "http://localhost:3001/mcp"
        assert c.enabled is True


class TestMCPToToolDef:
    def test_conversion(self):
        source = MCPToolSource()
        mcp_tool = FakeMCPTool(name="get_price", description="Get price")
        td = source._mcp_to_tooldef("finance", mcp_tool)

        assert td.name == "mcp_finance_get_price"
        assert td.source == "mcp"
        assert td.category == "external"
        assert td.description == "Get price"
        assert "symbol" in td.parameters.get("properties", {})
        assert callable(td.handler)

    def test_conversion_no_description(self):
        source = MCPToolSource()
        mcp_tool = FakeMCPTool(name="foo", description=None)
        td = source._mcp_to_tooldef("srv", mcp_tool)
        assert "MCP tool: foo" in td.description

    def test_conversion_no_schema(self):
        source = MCPToolSource()
        mcp_tool = FakeMCPTool(name="bar", inputSchema=None)
        td = source._mcp_to_tooldef("srv", mcp_tool)
        assert td.parameters == {"type": "object", "properties": {}}


class TestMCPToolSourceConnect:
    @pytest.mark.asyncio
    async def test_connect_stdio_success(self):
        """Test connecting to a stdio MCP server (mocked)."""
        fake_tools = [FakeMCPTool(name="get_price"), FakeMCPTool(name="get_volume")]
        fake_session = FakeSession(tools=fake_tools)

        config = MCPServerConfig(name="test-srv", transport="stdio", command="echo")

        with patch("mcp.client.stdio.stdio_client") as mock_stdio, \
             patch("mcp.ClientSession") as mock_cs:
            # stdio_client returns async context manager yielding (read, write)
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_stdio.return_value = mock_cm

            # ClientSession returns async context manager yielding session
            mock_session_cm = AsyncMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=False)
            mock_cs.return_value = mock_session_cm

            source = MCPToolSource()
            tool_defs = await source.connect(config)

            assert len(tool_defs) == 2
            assert tool_defs[0].name == "mcp_test-srv_get_price"
            assert tool_defs[1].name == "mcp_test-srv_get_volume"
            assert "test-srv" in source.connected_servers

    @pytest.mark.asyncio
    async def test_connect_sse_success(self):
        """Test connecting to an SSE MCP server (mocked)."""
        fake_tools = [FakeMCPTool(name="search_news")]
        fake_session = FakeSession(tools=fake_tools)

        config = MCPServerConfig(name="news-srv", transport="sse", url="http://localhost:3001/mcp")

        with patch("mcp.client.sse.sse_client") as mock_sse, \
             patch("mcp.ClientSession") as mock_cs:
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value = mock_cm

            mock_session_cm = AsyncMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=False)
            mock_cs.return_value = mock_session_cm

            source = MCPToolSource()
            tool_defs = await source.connect(config)

            assert len(tool_defs) == 1
            assert tool_defs[0].name == "mcp_news-srv_search_news"

    @pytest.mark.asyncio
    async def test_connect_stdio_missing_command(self):
        config = MCPServerConfig(name="bad", transport="stdio")
        source = MCPToolSource()
        with pytest.raises(RuntimeError, match="MCP connection failed"):
            await source.connect(config)

    @pytest.mark.asyncio
    async def test_connect_sse_missing_url(self):
        config = MCPServerConfig(name="bad", transport="sse")
        source = MCPToolSource()
        with pytest.raises(RuntimeError, match="MCP connection failed"):
            await source.connect(config)

    @pytest.mark.asyncio
    async def test_connect_unsupported_transport(self):
        config = MCPServerConfig(name="bad", transport="websocket", command="x")
        source = MCPToolSource()
        with pytest.raises(RuntimeError, match="MCP connection failed"):
            await source.connect(config)


class TestMCPToolSourceDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_connected(self):
        source = MCPToolSource()
        fake_stack = AsyncMock()
        from api.services.agent.mcp_client import _ServerConnection
        conn = _ServerConnection(
            config=MCPServerConfig(name="srv", transport="stdio"),
            session=FakeSession(),
            exit_stack=fake_stack,
        )
        source._connections["srv"] = conn
        assert "srv" in source.connected_servers

        await source.disconnect("srv")
        assert "srv" not in source.connected_servers
        fake_stack.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        source = MCPToolSource()
        await source.disconnect("nonexistent")  # should not raise

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        source = MCPToolSource()
        from api.services.agent.mcp_client import _ServerConnection
        for name in ["a", "b", "c"]:
            source._connections[name] = _ServerConnection(
                config=MCPServerConfig(name=name, transport="stdio"),
                session=FakeSession(),
                exit_stack=AsyncMock(),
            )
        await source.disconnect_all()
        assert len(source.connected_servers) == 0


class TestMCPToolSourceCallTool:
    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        source = MCPToolSource()
        fake_session = FakeSession(
            call_result=FakeToolResult(content=[FakeTextContent(text='{"price": 42.0}')])
        )
        from api.services.agent.mcp_client import _ServerConnection
        source._connections["srv"] = _ServerConnection(
            config=MCPServerConfig(name="srv", transport="stdio"),
            session=fake_session,
        )

        result = await source.call_tool("srv", "get_price", {"symbol": "AAPL"})
        assert result["result"] == '{"price": 42.0}'
        assert result["is_error"] is False

    @pytest.mark.asyncio
    async def test_call_tool_server_not_connected(self):
        source = MCPToolSource()
        with pytest.raises(KeyError, match="not connected"):
            await source.call_tool("nonexistent", "tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_error_result(self):
        source = MCPToolSource()
        fake_session = FakeSession(
            call_result=FakeToolResult(content=[FakeTextContent(text="error msg")], isError=True)
        )
        from api.services.agent.mcp_client import _ServerConnection
        source._connections["srv"] = _ServerConnection(
            config=MCPServerConfig(name="srv", transport="stdio"),
            session=fake_session,
        )

        result = await source.call_tool("srv", "bad_tool", {})
        assert result["is_error"] is True


class TestMCPToolSourceGetTools:
    def test_get_tools_empty(self):
        source = MCPToolSource()
        assert source.get_tools() == []

    def test_get_tools_multiple_servers(self):
        source = MCPToolSource()
        from api.services.agent.mcp_client import _ServerConnection
        source._connections["a"] = _ServerConnection(
            config=MCPServerConfig(name="a", transport="stdio"),
            tools=[FakeMCPTool(name="tool1")],
        )
        source._connections["b"] = _ServerConnection(
            config=MCPServerConfig(name="b", transport="sse"),
            tools=[FakeMCPTool(name="tool2"), FakeMCPTool(name="tool3")],
        )
        tools = source.get_tools()
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert names == {"mcp_a_tool1", "mcp_b_tool2", "mcp_b_tool3"}


# ---------------------------------------------------------------------------
# T37: ToolRegistry MCP integration tests
# ---------------------------------------------------------------------------

class TestToolRegistryMCPIntegration:
    @pytest.mark.asyncio
    async def test_load_mcp_tools(self):
        registry = ToolRegistry()
        # Pre-register a builtin tool
        builtin = ToolDef(
            name="query_portfolio", description="test", parameters={},
            source="builtin", handler=AsyncMock(), category="data",
        )
        registry.register_builtin(builtin)

        # Create a mock MCPToolSource with get_tools returning 2 tools
        mock_source = MagicMock()
        mock_source.get_tools.return_value = [
            ToolDef(name="mcp_srv_tool1", description="t1", parameters={},
                    source="mcp", handler=AsyncMock(), category="external"),
            ToolDef(name="mcp_srv_tool2", description="t2", parameters={},
                    source="mcp", handler=AsyncMock(), category="external"),
        ]

        count = await registry.load_mcp_tools(mock_source)
        assert count == 2
        assert registry.get_tool("mcp_srv_tool1") is not None
        assert registry.get_tool("mcp_srv_tool2") is not None
        # Builtin still exists
        assert registry.get_tool("query_portfolio") is not None

    def test_unregister_by_prefix(self):
        registry = ToolRegistry()
        for name in ["mcp_srv_a", "mcp_srv_b", "builtin_x"]:
            registry.register(ToolDef(
                name=name, description="", parameters={},
                source="mcp" if name.startswith("mcp") else "builtin",
                handler=AsyncMock(), category="data",
            ))
        removed = registry.unregister_by_prefix("mcp_srv_")
        assert removed == 2
        assert registry.get_tool("mcp_srv_a") is None
        assert registry.get_tool("builtin_x") is not None

    def test_unregister_by_prefix_no_match(self):
        registry = ToolRegistry()
        registry.register(ToolDef(
            name="builtin_x", description="", parameters={},
            source="builtin", handler=AsyncMock(), category="data",
        ))
        removed = registry.unregister_by_prefix("mcp_")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_mcp_failure_does_not_break_builtins(self):
        """If MCP loading fails, builtin tools remain functional."""
        registry = ToolRegistry()
        builtin = ToolDef(
            name="query_portfolio", description="test", parameters={},
            source="builtin", handler=AsyncMock(return_value={"ok": True}),
            category="data",
        )
        registry.register_builtin(builtin)

        # Mock MCPToolSource that raises on connect
        mock_source = MagicMock()
        mock_source.get_tools.side_effect = RuntimeError("MCP down")

        with pytest.raises(RuntimeError):
            await registry.load_mcp_tools(mock_source)

        # Builtin still works
        assert registry.get_tool("query_portfolio") is not None
        all_tools = registry.get_all_tools()
        assert len(all_tools) == 1


# ---------------------------------------------------------------------------
# T36: MCP API schema tests
# ---------------------------------------------------------------------------

class TestMCPSchemas:
    def test_mcp_server_create_valid(self):
        from api.schemas.agent import MCPServerCreate
        s = MCPServerCreate(name="test-srv", transport="stdio", command="echo")
        assert s.name == "test-srv"
        assert s.transport == "stdio"

    def test_mcp_server_create_invalid_name(self):
        from api.schemas.agent import MCPServerCreate
        with pytest.raises(Exception):
            MCPServerCreate(name="bad name!", transport="stdio")

    def test_mcp_server_create_invalid_transport(self):
        from api.schemas.agent import MCPServerCreate
        with pytest.raises(Exception):
            MCPServerCreate(name="test", transport="websocket")

    def test_mcp_server_out(self):
        from api.schemas.agent import MCPServerOut
        s = MCPServerOut(name="test", transport="sse", description="", enabled=True, tool_count=3, connected=True)
        assert s.tool_count == 3
        assert s.connected is True


# ---------------------------------------------------------------------------
# T38: End-to-end MCP flow test
# ---------------------------------------------------------------------------

class TestMCPE2EFlow:
    @pytest.mark.asyncio
    async def test_full_flow_connect_discover_call(self):
        """Simulate: connect -> discover tools -> register -> call tool via handler."""
        source = MCPToolSource()

        # Manually inject a connection with fake session
        fake_tools = [
            FakeMCPTool(name="get_stock_price", description="Get real-time stock price"),
            FakeMCPTool(name="get_market_news", description="Search market news"),
        ]
        from api.services.agent.mcp_client import _ServerConnection
        fake_session = FakeSession(
            tools=fake_tools,
            call_result=FakeToolResult(content=[FakeTextContent(text='{"price": 155.2}')]),
        )
        source._connections["finance-data"] = _ServerConnection(
            config=MCPServerConfig(name="finance-data", transport="stdio"),
            session=fake_session,
            tools=fake_tools,
        )

        # 1. Discover tools
        tool_defs = source.get_tools()
        assert len(tool_defs) == 2
        assert all(td.source == "mcp" for td in tool_defs)

        # 2. Register into ToolRegistry
        registry = ToolRegistry()
        count = await registry.load_mcp_tools(source)
        assert count == 2

        # 3. Verify tools are in registry
        t = registry.get_tool("mcp_finance-data_get_stock_price")
        assert t is not None
        assert t.source == "mcp"
        assert t.category == "external"

        # 4. Execute tool via registry (simulates orchestrator calling it)
        ctx = MagicMock(spec=AgentContext)
        result = await registry.execute("mcp_finance-data_get_stock_price", {"symbol": "AAPL"}, ctx)
        assert result.success is True
        assert '155.2' in str(result.result)

        # 5. Check OpenAI tool format
        openai_tools = [td.to_openai_tool() for td in tool_defs]
        assert all(t["type"] == "function" for t in openai_tools)
        assert openai_tools[0]["function"]["name"] == "mcp_finance-data_get_stock_price"

    @pytest.mark.asyncio
    async def test_full_flow_disconnect_removes_tools(self):
        """Connect -> register -> disconnect -> tools removed from registry."""
        source = MCPToolSource()
        from api.services.agent.mcp_client import _ServerConnection
        source._connections["srv"] = _ServerConnection(
            config=MCPServerConfig(name="srv", transport="stdio"),
            session=FakeSession(tools=[FakeMCPTool(name="tool1")]),
            exit_stack=AsyncMock(),
            tools=[FakeMCPTool(name="tool1")],
        )

        registry = ToolRegistry()
        await registry.load_mcp_tools(source)
        assert registry.get_tool("mcp_srv_tool1") is not None

        # Disconnect and clean up registry
        await source.disconnect("srv")
        removed = registry.unregister_by_prefix("mcp_srv_")
        assert removed == 1
        assert registry.get_tool("mcp_srv_tool1") is None
