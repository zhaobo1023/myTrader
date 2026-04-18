# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Models - Agent conversations and messages.
"""
from datetime import datetime, timezone


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, DateTime,
    Enum, JSON, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


class AgentConversation(Base):
    __tablename__ = 'agent_conversations'

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(200), default='', nullable=False)
    active_skill = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False,
    )

    # Relationships
    messages = relationship(
        'AgentMessage',
        back_populates='conversation',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='AgentMessage.created_at',
    )

    __table_args__ = (
        Index('ix_agent_conv_user_id', 'user_id'),
        Index('ix_agent_conv_updated_at', 'updated_at'),
    )

    def __repr__(self):
        return f'<AgentConversation id={self.id} user_id={self.user_id}>'


class AgentMessage(Base):
    __tablename__ = 'agent_messages'

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36),
        ForeignKey('agent_conversations.id', ondelete='CASCADE'),
        nullable=False,
    )
    role = Column(Enum('user', 'assistant', 'tool', name='agent_msg_role'), nullable=False)
    content = Column(Text, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    tool_call_id = Column(String(100), nullable=True)
    tool_name = Column(String(100), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    # Relationships
    conversation = relationship('AgentConversation', back_populates='messages')

    __table_args__ = (
        Index('ix_agent_msg_conversation_id', 'conversation_id'),
        Index('ix_agent_msg_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<AgentMessage id={self.id} role={self.role}>'

    def to_llm_dict(self) -> dict:
        """Convert to OpenAI message format for LLM context."""
        msg: dict = {"role": self.role, "content": self.content or ""}
        if self.role == "assistant" and self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.role == "tool":
            msg["tool_call_id"] = self.tool_call_id or ""
            msg["name"] = self.tool_name or ""
        return msg
