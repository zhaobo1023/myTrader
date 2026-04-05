# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - Subscription
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Date,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


class Subscription(Base):
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    plan = Column(String(50), nullable=False, default='free')
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='subscription')

    def __repr__(self):
        return f'<Subscription user_id={self.user_id} plan={self.plan}>'
