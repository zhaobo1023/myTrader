# -*- coding: utf-8 -*-
"""
ConversationStore - manages conversation lifecycle and message persistence.

Handles: creation, message saving, history loading, context compression,
listing, and deletion. Uses Redis for short-term cache.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import select, delete, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import AgentConversation, AgentMessage

logger = logging.getLogger('myTrader.agent.conversation')

# Redis key patterns
_REDIS_MESSAGES_KEY = "agent:conv:{conv_id}:messages"
_REDIS_MESSAGES_TTL = 7200  # 2 hours


class ConversationStore:
    """Manage agent conversations and messages."""

    def __init__(self, db: AsyncSession, redis: Optional[aioredis.Redis] = None):
        self.db = db
        self.redis = redis

    # ------------------------------------------------------------------
    # Conversation CRUD
    # ------------------------------------------------------------------

    async def create(self, user_id: int, title: str = "") -> str:
        """Create a new conversation, return its UUID."""
        conv_id = str(uuid.uuid4())
        conv = AgentConversation(
            id=conv_id,
            user_id=user_id,
            title=title or "",
        )
        self.db.add(conv)
        await self.db.flush()
        return conv_id

    async def get_conversation(
        self, conv_id: str, user_id: Optional[int] = None
    ) -> Optional[AgentConversation]:
        """Fetch a conversation by ID. Optionally filter by user_id for ownership check."""
        stmt = select(AgentConversation).where(AgentConversation.id == conv_id)
        if user_id is not None:
            stmt = stmt.where(AgentConversation.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_conversations(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """List conversations for a user, ordered by updated_at desc."""
        # Get conversations
        stmt = (
            select(AgentConversation)
            .where(AgentConversation.user_id == user_id)
            .order_by(desc(AgentConversation.updated_at))
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        convs = result.scalars().all()

        items = []
        for conv in convs:
            # Count messages
            count_stmt = (
                select(func.count(AgentMessage.id))
                .where(AgentMessage.conversation_id == conv.id)
            )
            count_result = await self.db.execute(count_stmt)
            msg_count = count_result.scalar() or 0

            items.append({
                "id": conv.id,
                "title": conv.title or "",
                "active_skill": conv.active_skill,
                "message_count": msg_count,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            })
        return items

    async def delete_conversation(self, conv_id: str, user_id: int) -> bool:
        """Delete a conversation and all its messages. Returns True if deleted."""
        conv = await self.get_conversation(conv_id, user_id)
        if conv is None:
            return False

        # Delete messages first
        await self.db.execute(
            delete(AgentMessage).where(AgentMessage.conversation_id == conv_id)
        )
        await self.db.execute(
            delete(AgentConversation).where(AgentConversation.id == conv_id)
        )
        await self.db.flush()

        # Clear Redis cache
        await self._clear_cache(conv_id)
        return True

    async def update_title(self, conv_id: str, title: str) -> None:
        """Update conversation title."""
        conv = await self.get_conversation(conv_id)
        if conv:
            conv.title = title
            await self.db.flush()

    async def set_active_skill(self, conv_id: str, skill_name: Optional[str]) -> None:
        """Set or clear the active plugin skill for a conversation."""
        conv = await self.get_conversation(conv_id)
        if conv:
            conv.active_skill = skill_name
            await self.db.flush()

    # ------------------------------------------------------------------
    # Message operations
    # ------------------------------------------------------------------

    async def save_message(
        self,
        conv_id: str,
        role: str,
        content: Optional[str] = None,
        tool_calls: Optional[list[dict]] = None,
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AgentMessage:
        """Save a message to the conversation."""
        msg = AgentMessage(
            conversation_id=conv_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            metadata_json=metadata,
        )
        self.db.add(msg)
        await self.db.flush()

        # Update conversation timestamp
        conv = await self.get_conversation(conv_id)
        if conv:
            conv.updated_at = _utcnow()
            # Auto-generate title from first user message
            if not conv.title and role == "user" and content:
                conv.title = content[:30].strip()
            await self.db.flush()

        # Invalidate Redis cache
        await self._clear_cache(conv_id)

        return msg

    async def get_messages(self, conv_id: str, limit: int = 50) -> list[dict]:
        """Get recent messages for a conversation, ordered by created_at asc."""
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conv_id)
            .order_by(AgentMessage.created_at.asc())
        )
        result = await self.db.execute(stmt)
        all_msgs = result.scalars().all()

        # Take the last `limit` messages
        msgs = all_msgs[-limit:] if len(all_msgs) > limit else all_msgs

        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "tool_calls": msg.tool_calls,
                "tool_call_id": msg.tool_call_id,
                "tool_name": msg.tool_name,
                "metadata": msg.metadata_json,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in msgs
        ]

    async def get_messages_for_llm(
        self, conv_id: str, max_messages: int = 20
    ) -> list[dict]:
        """Get messages formatted for LLM context (OpenAI message format).

        Returns the most recent `max_messages` messages in LLM-compatible format.
        """
        # Try Redis cache first
        cached = await self._get_cached_messages(conv_id)
        if cached is not None:
            return cached[-max_messages:]

        stmt = (
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conv_id)
            .order_by(AgentMessage.created_at.asc())
        )
        result = await self.db.execute(stmt)
        all_msgs = result.scalars().all()

        # Take last N messages
        recent = all_msgs[-max_messages:] if len(all_msgs) > max_messages else all_msgs
        llm_messages = [msg.to_llm_dict() for msg in recent]

        # Cache in Redis
        await self._cache_messages(conv_id, llm_messages)

        return llm_messages

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    async def _get_cached_messages(self, conv_id: str) -> Optional[list[dict]]:
        if self.redis is None:
            return None
        try:
            key = _REDIS_MESSAGES_KEY.format(conv_id=conv_id)
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug('[ConversationStore] Redis cache miss: %s', e)
        return None

    async def _cache_messages(self, conv_id: str, messages: list[dict]) -> None:
        if self.redis is None:
            return
        try:
            key = _REDIS_MESSAGES_KEY.format(conv_id=conv_id)
            await self.redis.set(key, json.dumps(messages, ensure_ascii=False), ex=_REDIS_MESSAGES_TTL)
        except Exception as e:
            logger.debug('[ConversationStore] Redis cache write failed: %s', e)

    async def _clear_cache(self, conv_id: str) -> None:
        if self.redis is None:
            return
        try:
            key = _REDIS_MESSAGES_KEY.format(conv_id=conv_id)
            await self.redis.delete(key)
        except Exception:
            pass
