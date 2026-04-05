# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - Backtest Job
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Enum,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


class JobStatus(str, enum.Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    DONE = 'done'
    FAILED = 'failed'


class BacktestJob(Base):
    __tablename__ = 'backtest_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id', ondelete='SET NULL'), nullable=True)
    task_id = Column(String(100), unique=True, nullable=True)  # Celery task ID
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    params = Column(JSON, nullable=True)  # backtest parameters

    # Results
    total_return = Column(Float, nullable=True)
    annual_return = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    ic = Column(Float, nullable=True)
    icir = Column(Float, nullable=True)
    result_file = Column(String(500), nullable=True)  # path to result file
    error_msg = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    # Relationships
    strategy = relationship('Strategy', back_populates='backtest_jobs')

    def __repr__(self):
        return f'<BacktestJob id={self.id} status={self.status} task_id={self.task_id}>'
