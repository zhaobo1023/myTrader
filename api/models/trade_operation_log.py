# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - TradeOperationLog (调仓操作日志)
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Index,
)

from api.dependencies import Base


class TradeOperationLog(Base):
    __tablename__ = 'trade_operation_logs'
    __table_args__ = (
        Index('ix_trade_log_user_id', 'user_id'),
        Index('ix_trade_log_user_type', 'user_id', 'operation_type'),
        Index('ix_trade_log_created_at', 'created_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    operation_type = Column(String(20), nullable=False)
    stock_code = Column(String(20), nullable=False, default='')
    stock_name = Column(String(50), nullable=True)
    detail = Column(String(500), nullable=True)
    before_value = Column(String(200), nullable=True)
    after_value = Column(String(200), nullable=True)
    source = Column(String(20), nullable=False, default='auto')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<TradeOperationLog user={self.user_id} type={self.operation_type} stock={self.stock_code}>'
