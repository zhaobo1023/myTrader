# -*- coding: utf-8 -*-
"""
Agent API routes - chat, conversation management, tool listing.

POST /api/agent/chat           - SSE streaming chat
GET  /api/agent/conversations  - List conversations
GET  /api/agent/conversations/:id - Conversation detail
DELETE /api/agent/conversations/:id - Delete conversation
GET  /api/agent/tools          - Available tools list
"""
from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_redis
from api.middleware.auth import get_current_user
from api.models.user import User
from api.middleware.auth import require_admin
from api.schemas.agent import (
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    MCPServerCreate,
    MCPServerOut,
    MessageOut,
    ToolInfo,
)

logger = logging.getLogger('myTrader.agent.router')

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _get_orchestrator(db: AsyncSession, redis: aioredis.Redis):
    """Build an AgentOrchestrator with all dependencies."""
    from api.services.agent.conversation import ConversationStore
    from api.services.agent.llm_chat import AgentLLMClient
    from api.services.agent.orchestrator import AgentOrchestrator
    from api.services.agent.tool_registry import get_registry

    # Ensure builtin tools are loaded (import triggers @builtin_tool decorators)
    import api.services.agent.builtin_tools  # noqa: F401

    store = ConversationStore(db, redis)
    llm_client = AgentLLMClient()
    registry = get_registry()

    return AgentOrchestrator(
        tool_registry=registry,
        llm_client=llm_client,
        conversation_store=store,
    )


async def _sse_generator(orchestrator, req: ChatRequest, user: User, db, redis):
    """Wrap orchestrator.chat() into SSE text stream."""
    try:
        async for event in orchestrator.chat(
            message=req.message,
            user=user,
            db=db,
            redis=redis,
            conversation_id=req.conversation_id,
            active_skill=req.active_skill,
            page_context=req.page_context,
        ):
            data = json.dumps(event, ensure_ascii=False)
            yield f"data: {data}\n\n"
    except Exception as e:
        logger.error('[agent/chat] SSE error: %s', e, exc_info=True)
        err = json.dumps({"type": "error", "message": str(e), "code": "sse_error"})
        yield f"data: {err}\n\n"


@router.post("/chat")
async def agent_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """SSE streaming chat endpoint."""
    orchestrator = _get_orchestrator(db, redis)
    return StreamingResponse(
        _sse_generator(orchestrator, req, current_user, db, redis),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """List user's conversations."""
    from api.services.agent.conversation import ConversationStore
    store = ConversationStore(db, redis)
    convs = await store.list_conversations(current_user.id, limit=limit, offset=offset)
    return convs


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Get conversation detail with messages."""
    from api.services.agent.conversation import ConversationStore
    store = ConversationStore(db, redis)
    conv = await store.get_conversation(conversation_id, user_id=current_user.id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")

    messages = await store.get_messages(conversation_id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title or "",
        active_skill=conv.active_skill,
        messages=[MessageOut(**m) for m in messages],
        created_at=conv.created_at.isoformat() if conv.created_at else None,
        updated_at=conv.updated_at.isoformat() if conv.updated_at else None,
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Delete a conversation."""
    from api.services.agent.conversation import ConversationStore
    store = ConversationStore(db, redis)
    deleted = await store.delete_conversation(conversation_id, current_user.id)
    if not deleted:
        raise HTTPException(404, "Conversation not found")
    return {"ok": True}


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools(
    current_user: User = Depends(get_current_user),
):
    """List available tools for the current user (filtered by tier)."""
    from api.services.agent.tool_registry import get_registry
    import api.services.agent.builtin_tools  # noqa: F401

    registry = get_registry()
    tools = registry.get_tools_for_user(current_user)
    return [ToolInfo(**t.to_info_dict()) for t in tools]


# ---------------------------------------------------------------------------
# MCP Server management (admin only)
# ---------------------------------------------------------------------------

# In-memory MCP state (per-process). For production, configs should be
# persisted to DB / env and loaded at startup.
_mcp_source = None
_mcp_configs: dict[str, "MCPServerConfig"] = {}


def _get_mcp_source():
    """Lazy-init global MCPToolSource singleton."""
    global _mcp_source
    if _mcp_source is None:
        from api.services.agent.mcp_client import MCPToolSource
        _mcp_source = MCPToolSource()
    return _mcp_source


@router.post("/mcp/servers", response_model=MCPServerOut)
async def register_mcp_server(
    req: MCPServerCreate,
    _admin: User = Depends(require_admin),
):
    """Register and connect an MCP Server (admin only)."""
    from api.services.agent.mcp_client import MCPServerConfig
    from api.services.agent.tool_registry import get_registry

    config = MCPServerConfig(
        name=req.name,
        transport=req.transport,
        description=req.description,
        command=req.command,
        args=req.args,
        url=req.url,
        enabled=req.enabled,
    )

    mcp_source = _get_mcp_source()
    tool_defs = await mcp_source.connect(config)

    # Register only this server's tools into ToolRegistry
    registry = get_registry()
    await registry.load_mcp_tools(mcp_source, server_name=req.name)

    _mcp_configs[req.name] = config

    return MCPServerOut(
        name=config.name,
        transport=config.transport,
        description=config.description,
        enabled=config.enabled,
        tool_count=len(tool_defs),
        connected=True,
    )


@router.get("/mcp/servers", response_model=list[MCPServerOut])
async def list_mcp_servers(
    _admin: User = Depends(require_admin),
):
    """List registered MCP Servers (admin only)."""
    mcp_source = _get_mcp_source()
    connected = set(mcp_source.connected_servers)
    results = []
    for name, config in _mcp_configs.items():
        is_connected = name in connected
        tool_count = len([t for t in mcp_source.get_tools() if t.name.startswith(f"mcp_{name}_")]) if is_connected else 0
        results.append(MCPServerOut(
            name=config.name,
            transport=config.transport,
            description=config.description,
            enabled=config.enabled,
            tool_count=tool_count,
            connected=is_connected,
        ))
    return results


@router.delete("/mcp/servers/{server_name}")
async def delete_mcp_server(
    server_name: str,
    _admin: User = Depends(require_admin),
):
    """Disconnect and remove an MCP Server (admin only)."""
    from api.services.agent.tool_registry import get_registry

    if server_name not in _mcp_configs:
        raise HTTPException(404, f"MCP server '{server_name}' not found")

    mcp_source = _get_mcp_source()
    await mcp_source.disconnect(server_name)

    # Remove tools from registry
    registry = get_registry()
    removed = registry.unregister_by_prefix(f"mcp_{server_name}_")

    _mcp_configs.pop(server_name, None)

    return {"ok": True, "tools_removed": removed}


@router.post("/mcp/servers/{server_name}/reconnect", response_model=MCPServerOut)
async def reconnect_mcp_server(
    server_name: str,
    _admin: User = Depends(require_admin),
):
    """Reconnect to an MCP Server (admin only)."""
    from api.services.agent.tool_registry import get_registry

    config = _mcp_configs.get(server_name)
    if config is None:
        raise HTTPException(404, f"MCP server '{server_name}' not found")

    mcp_source = _get_mcp_source()
    tool_defs = await mcp_source.connect(config)

    registry = get_registry()
    await registry.load_mcp_tools(mcp_source, server_name=server_name)

    return MCPServerOut(
        name=config.name,
        transport=config.transport,
        description=config.description,
        enabled=config.enabled,
        tool_count=len(tool_defs),
        connected=True,
    )
