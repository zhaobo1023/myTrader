# -*- coding: utf-8 -*-
"""
Agent core data structures: ToolDef, AgentContext, ToolCallResult.

All agent tools (builtin / plugin / mcp) share the same ToolDef protocol.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolDef:
    """Unified tool definition for all three sources."""
    name: str               # unique identifier, e.g. "query_portfolio"
    description: str        # LLM uses this to decide when to call
    parameters: dict        # JSON Schema (OpenAI tools format)
    source: str             # "builtin" | "plugin" | "mcp"
    handler: Callable[..., Awaitable[dict]]  # async (params, ctx) -> dict
    requires_tier: str = "free"   # "free" | "pro"
    category: str = "data"        # "data" | "analysis" | "action" | "external"

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function calling tools format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_info_dict(self) -> dict:
        """Convert to API-friendly info dict (no handler)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "source": self.source,
            "category": self.category,
            "requires_tier": self.requires_tier,
        }


@dataclass
class AgentContext:
    """Runtime context passed to every tool handler."""
    user: Any               # api.models.user.User
    db: AsyncSession
    redis: aioredis.Redis
    conversation_id: str
    page_context: dict = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """Result of executing a single tool."""
    name: str
    result: dict
    call_id: str
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""


class ToolCallTimer:
    """Context manager to measure tool execution time."""

    def __init__(self):
        self.start: float = 0.0
        self.duration_ms: float = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.duration_ms = (time.monotonic() - self.start) * 1000
