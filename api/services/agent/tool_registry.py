# -*- coding: utf-8 -*-
"""
ToolRegistry - unified registration and discovery for all tool sources.

Three sources: builtin / plugin / mcp, all share the ToolDef protocol.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable, Optional

from api.services.agent.schemas import AgentContext, ToolCallResult, ToolDef

logger = logging.getLogger('myTrader.agent.registry')


class ToolRegistry:
    """Central registry for all agent tools."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        """Register a tool. Raises ValueError on duplicate name."""
        if tool_def.name in self._tools:
            raise ValueError(f"Tool '{tool_def.name}' already registered")
        self._tools[tool_def.name] = tool_def
        logger.info('[ToolRegistry] registered %s (source=%s)', tool_def.name, tool_def.source)

    def register_builtin(self, tool_def: ToolDef) -> None:
        tool_def.source = "builtin"
        self.register(tool_def)

    def register_plugin(self, tool_def: ToolDef) -> None:
        tool_def.source = "plugin"
        self.register(tool_def)

    def register_mcp(self, tool_def: ToolDef) -> None:
        tool_def.source = "mcp"
        self.register(tool_def)

    def unregister_by_prefix(self, prefix: str) -> int:
        """Remove all tools whose name starts with prefix. Returns count removed."""
        to_remove = [name for name in self._tools if name.startswith(prefix)]
        for name in to_remove:
            del self._tools[name]
        if to_remove:
            logger.info('[ToolRegistry] unregistered %d tools with prefix "%s"', len(to_remove), prefix)
        return len(to_remove)

    async def load_mcp_tools(self, mcp_source, server_name: str = "") -> int:
        """Load tools from an MCPToolSource into the registry.

        If server_name is provided, only loads tools for that server
        (replacing existing ones with the same prefix). Otherwise loads all.
        Returns number of tools loaded.
        """
        if server_name:
            tool_defs = [
                td for td in mcp_source.get_tools()
                if td.name.startswith(f"mcp_{server_name}_")
            ]
        else:
            tool_defs = mcp_source.get_tools()

        count = 0
        for td in tool_defs:
            self._tools.pop(td.name, None)
            self.register_mcp(td)
            count += 1
        logger.info('[ToolRegistry] loaded %d MCP tools', count)
        return count

    def unregister(self, name: str) -> None:
        """Remove a tool by name. No-op if not found."""
        self._tools.pop(name, None)

    def get_tool(self, name: str) -> Optional[ToolDef]:
        """Lookup a tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> list[ToolDef]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_tools_for_user(self, user: Any) -> list[ToolDef]:
        """Filter tools by user tier.

        Free users see only free tools.
        Pro users and admins see all tools.
        """
        user_tier = getattr(user, 'tier', None)
        if user_tier is None:
            return [t for t in self._tools.values() if t.requires_tier == "free"]

        tier_value = user_tier.value if hasattr(user_tier, 'value') else str(user_tier)
        user_role = getattr(user, 'role', None)
        role_value = user_role.value if hasattr(user_role, 'value') else str(user_role) if user_role else ""

        if tier_value == "pro" or role_value == "admin":
            return list(self._tools.values())

        return [t for t in self._tools.values() if t.requires_tier == "free"]

    def get_openai_tools(self, user: Any) -> list[dict]:
        """Convert user-accessible tools to OpenAI function calling format."""
        return [t.to_openai_tool() for t in self.get_tools_for_user(user)]

    async def execute(
        self, name: str, params: dict, ctx: AgentContext
    ) -> ToolCallResult:
        """Execute a tool by name.

        Returns ToolCallResult with timing info.
        Raises KeyError if tool not found.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found in registry")

        import time
        start = time.monotonic()
        try:
            result = await tool.handler(params, ctx)
            duration_ms = (time.monotonic() - start) * 1000
            return ToolCallResult(
                name=name,
                result=result,
                call_id="",  # caller sets this
                duration_ms=duration_ms,
                success=True,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error('[ToolRegistry] tool %s failed: %s', name, e, exc_info=True)
            return ToolCallResult(
                name=name,
                result={},
                call_id="",
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Return the global ToolRegistry singleton."""
    return _registry


# ---------------------------------------------------------------------------
# Decorator for builtin tools
# ---------------------------------------------------------------------------

def builtin_tool(
    name: str,
    description: str,
    parameters: dict,
    category: str = "data",
    requires_tier: str = "free",
):
    """Decorator to register an async function as a builtin tool.

    Usage::

        @builtin_tool(
            name="query_portfolio",
            description="...",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        async def query_portfolio(params: dict, ctx: AgentContext) -> dict:
            ...
    """
    def decorator(fn: Callable[..., Awaitable[dict]]):
        tool_def = ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            source="builtin",
            handler=fn,
            requires_tier=requires_tier,
            category=category,
        )
        _registry.register_builtin(tool_def)
        # Attach metadata for introspection
        fn._tool_def = tool_def
        return fn
    return decorator
