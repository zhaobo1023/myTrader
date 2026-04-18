# -*- coding: utf-8 -*-
"""
Pydantic schemas for Agent API endpoints.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/agent/chat request body."""
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID")
    active_skill: Optional[str] = Field(None, description="Activated plugin skill name")
    page_context: Optional[dict[str, Any]] = Field(None, description="Frontend page context")


class ConversationSummary(BaseModel):
    """Conversation list item."""
    id: str
    title: str
    active_skill: Optional[str] = None
    message_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MessageOut(BaseModel):
    """Single message in conversation detail."""
    id: int
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[str] = None


class ConversationDetail(BaseModel):
    """GET /api/agent/conversations/:id response."""
    id: str
    title: str
    active_skill: Optional[str] = None
    messages: list[MessageOut] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ToolInfo(BaseModel):
    """Tool information for GET /api/agent/tools."""
    name: str
    description: str
    parameters: dict
    source: str
    category: str
    requires_tier: str


class MCPServerCreate(BaseModel):
    """POST /api/agent/mcp/servers request body."""
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    transport: str = Field(..., pattern=r"^(stdio|sse)$")
    description: str = Field("", max_length=500)
    command: Optional[str] = None
    args: list[str] = []
    url: Optional[str] = None
    enabled: bool = True


class MCPServerOut(BaseModel):
    """MCP Server info response."""
    name: str
    transport: str
    description: str
    enabled: bool
    tool_count: int = 0
    connected: bool = False
