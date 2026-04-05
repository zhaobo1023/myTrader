# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - User
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Boolean,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


class UserTier(str, enum.Enum):
    FREE = 'free'
    PRO = 'pro'


class UserRole(str, enum.Enum):
    USER = 'user'
    ADMIN = 'admin'


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    tier = Column(Enum(UserTier), default=UserTier.FREE, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    subscription = relationship('Subscription', back_populates='user', uselist=False)
    usage_logs = relationship('UsageLog', back_populates='user')
    api_keys = relationship('ApiKey', back_populates='user')

    def __repr__(self):
        return f'<User id={self.id} email={self.email} tier={self.tier}>'
