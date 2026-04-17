# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - InboxMessage
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index,
)

from api.dependencies import Base


class InboxMessage(Base):
    __tablename__ = 'inbox_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    message_type = Column(String(30), nullable=False)  # daily_report, alert, system, strategy_signal
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)  # Markdown content
    metadata_json = Column(Text, nullable=True)  # JSON for structured data
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index('ix_inbox_user_read_created', 'user_id', 'is_read', 'created_at'),
    )
