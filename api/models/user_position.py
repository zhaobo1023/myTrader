# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - UserPosition
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey,
    UniqueConstraint,
)

from api.dependencies import Base


class UserPosition(Base):
    __tablename__ = 'user_positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(50), nullable=True)
    level = Column(String(10), nullable=True)  # L1/L2/L3
    shares = Column(Integer, nullable=True)
    cost_price = Column(Float, nullable=True)
    account = Column(String(50), nullable=True)
    note = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'stock_code', 'account', name='uq_user_position'),
    )
