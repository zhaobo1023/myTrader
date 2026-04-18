# -*- coding: utf-8 -*-
"""
MCPToolSource - manages connections to multiple MCP Servers,
discovers their tools, and proxies tool calls.

Uses the official `mcp` Python SDK (pip install mcp).
"""
from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Optional

from api.services.agent.schemas import AgentContext, ToolDef

logger = logging.getLogger("myTrader.agent.mcp")


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP Server."""
    name: str
    transport: str  # "stdio" | "sse"
    description: str = ""
    enabled: bool = True
    # stdio fields
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: Optional[dict[str, str]] = None
    # sse fields
    url: Optional[str] = None


@dataclass
class _ServerConnection:
    """Internal state for a connected MCP Server."""
    config: MCPServerConfig
    session: Any = None  # mcp.ClientSession
    exit_stack: Optional[AsyncExitStack] = None
    tools: list[dict] = field(default_factory=list)  # raw MCP Tool objects


class MCPToolSource:
    """Manages multiple MCP Server connections, discovers and calls tools."""

    def __init__(self):
        self._connections: dict[str, _ServerConnection] = {}

    @property
    def connected_servers(self) -> list[str]:
        return list(self._connections.keys())

    async def connect(self, config: MCPServerConfig) -> list[ToolDef]:
        """Connect to an MCP Server and discover its tools.

        Returns list of ToolDef converted from the server's tools.
        Raises RuntimeError on connection failure.
        """
        if config.name in self._connections:
            logger.warning("[MCP] server '%s' already connected, disconnecting first", config.name)
            await self.disconnect(config.name)

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.client.sse import sse_client

            exit_stack = AsyncExitStack()
            await exit_stack.__aenter__()

            if config.transport == "stdio":
                if not config.command:
                    raise ValueError(f"MCP server '{config.name}': stdio transport requires 'command'")
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env=config.env,
                )
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
            elif config.transport == "sse":
                if not config.url:
                    raise ValueError(f"MCP server '{config.name}': sse transport requires 'url'")
                read_stream, write_stream = await exit_stack.enter_async_context(
                    sse_client(config.url)
                )
            else:
                raise ValueError(f"Unsupported transport: {config.transport}")

            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()

            # Discover tools
            result = await session.list_tools()
            raw_tools = result.tools if result.tools else []

            conn = _ServerConnection(
                config=config,
                session=session,
                exit_stack=exit_stack,
                tools=raw_tools,
            )
            self._connections[config.name] = conn

            tool_defs = [self._mcp_to_tooldef(config.name, t) for t in raw_tools]
            logger.info(
                "[MCP] connected to '%s' (%s), discovered %d tools",
                config.name, config.transport, len(tool_defs),
            )
            return tool_defs

        except Exception as e:
            # Clean up on failure
            try:
                await exit_stack.__aexit__(type(e), e, e.__traceback__)
            except Exception:
                pass
            logger.error("[MCP] failed to connect to '%s': %s", config.name, e)
            raise RuntimeError(f"MCP connection failed for '{config.name}': {e}") from e

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP Server. No-op if not connected."""
        conn = self._connections.pop(server_name, None)
        if conn and conn.exit_stack:
            try:
                await conn.exit_stack.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("[MCP] error disconnecting '%s': %s", server_name, e)
        logger.info("[MCP] disconnected from '%s'", server_name)

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        names = list(self._connections.keys())
        for name in names:
            await self.disconnect(name)

    def get_tools(self) -> list[ToolDef]:
        """Return ToolDefs for all tools across all connected servers."""
        tool_defs = []
        for name, conn in self._connections.items():
            for raw_tool in conn.tools:
                tool_defs.append(self._mcp_to_tooldef(name, raw_tool))
        return tool_defs

    async def call_tool(
        self, server_name: str, tool_name: str, params: dict
    ) -> dict:
        """Call a tool on a specific MCP Server.

        Raises KeyError if server not connected.
        Raises RuntimeError on call failure.
        """
        conn = self._connections.get(server_name)
        if conn is None:
            raise KeyError(f"MCP server '{server_name}' not connected")

        try:
            result = await conn.session.call_tool(tool_name, arguments=params)
            # Convert CallToolResult to dict
            content_parts = []
            if result.content:
                for part in result.content:
                    if hasattr(part, "text"):
                        content_parts.append(part.text)
                    elif hasattr(part, "data"):
                        content_parts.append(str(part.data))
                    else:
                        content_parts.append(str(part))
            return {
                "result": "\n".join(content_parts) if content_parts else "",
                "is_error": getattr(result, "isError", False),
            }
        except Exception as e:
            logger.error("[MCP] call_tool failed: server=%s tool=%s err=%s", server_name, tool_name, e)
            raise RuntimeError(f"MCP tool call failed: {e}") from e

    def _mcp_to_tooldef(self, server_name: str, mcp_tool: Any) -> ToolDef:
        """Convert an MCP Tool object to our unified ToolDef."""
        prefixed_name = f"mcp_{server_name}_{mcp_tool.name}"

        # Build handler that proxies to call_tool
        _server_name = server_name
        _tool_name = mcp_tool.name

        async def _handler(params: dict, ctx: AgentContext) -> dict:
            return await self.call_tool(_server_name, _tool_name, params)

        return ToolDef(
            name=prefixed_name,
            description=mcp_tool.description or f"MCP tool: {mcp_tool.name}",
            parameters=mcp_tool.inputSchema if mcp_tool.inputSchema else {"type": "object", "properties": {}},
            source="mcp",
            handler=_handler,
            requires_tier="free",
            category="external",
        )
