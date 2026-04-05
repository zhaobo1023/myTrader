# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - API Key (programmatic access)
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


class ApiKey(Base):
    __tablename__ = 'api_keys'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False, unique=True)
    key_prefix = Column(String(16), nullable=False)  # first 8 chars for display
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='api_keys')

    def __repr__(self):
        return f'<ApiKey user_id={self.user_id} prefix={self.key_prefix}>'
