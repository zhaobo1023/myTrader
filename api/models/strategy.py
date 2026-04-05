# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - Strategy
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


class Strategy(Base):
    __tablename__ = 'strategies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    params = Column(JSON, nullable=True)  # strategy parameters as JSON
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    backtest_jobs = relationship('BacktestJob', back_populates='strategy')

    def __repr__(self):
        return f'<Strategy id={self.id} name={self.name}>'
