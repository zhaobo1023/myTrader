# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - Usage Log (quota counting)
"""
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Date, ForeignKey, DateTime,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


class UsageLog(Base):
    __tablename__ = 'usage_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    api_endpoint = Column(String(255), nullable=False)
    usage_date = Column(Date, default=date.today, nullable=False, index=True)
    count = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='usage_logs')

    def __repr__(self):
        return f'<UsageLog user_id={self.user_id} endpoint={self.api_endpoint} date={self.usage_date} count={self.count}>'
