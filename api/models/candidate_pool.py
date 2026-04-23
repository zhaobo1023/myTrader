# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Models - Candidate Pool

Tables:
- candidate_pool_stocks: stocks in the candidate watchlist
- candidate_monitor_daily: daily technical snapshot per stock
"""
import enum
import json
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Double,
    Enum, UniqueConstraint, Index,
)

from api.dependencies import Base


class CandidateStatus(str, enum.Enum):
    WATCHING = 'watching'
    FOCUSED = 'focused'
    EXCLUDED = 'excluded'


class AlertLevel(str, enum.Enum):
    RED = 'red'
    YELLOW = 'yellow'
    GREEN = 'green'
    INFO = 'info'


class CandidatePoolStock(Base):
    __tablename__ = 'candidate_pool_stocks'
    __table_args__ = (
        UniqueConstraint('user_id', 'stock_code', name='uq_candidate_user_stock'),
        Index('ix_candidate_pool_stocks_user', 'user_id'),
        Index('ix_candidate_pool_stocks_source', 'user_id', 'source_type', 'add_date'),
        Index('ix_candidate_pool_stocks_status', 'user_id', 'status'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, default=0)
    stock_code = Column(String(12), nullable=False)
    stock_name = Column(String(20), nullable=False, default='')

    # source
    source_type = Column(
        Enum('industry', 'strategy', 'manual', name='candidate_source_type'),
        nullable=False,
    )
    source_detail = Column(String(100), nullable=True)   # industry_name or strategy_name

    # snapshot at time of add (JSON string)
    entry_snapshot = Column(Text, nullable=True)

    add_date = Column(Date, nullable=False)
    status = Column(
        Enum('watching', 'focused', 'excluded', name='candidate_status'),
        nullable=False, default='watching',
    )
    memo = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def snapshot_dict(self) -> dict:
        if not self.entry_snapshot:
            return {}
        try:
            return json.loads(self.entry_snapshot)
        except Exception:
            return {}

    def __repr__(self):
        return f'<CandidatePoolStock code={self.stock_code} source={self.source_type}>'


class CandidateMonitorDaily(Base):
    __tablename__ = 'candidate_monitor_daily'
    __table_args__ = (
        UniqueConstraint('stock_code', 'trade_date', name='uq_candidate_monitor_code_date'),
        Index('ix_candidate_monitor_daily_date', 'trade_date'),
        Index('ix_candidate_monitor_daily_alert', 'trade_date', 'alert_level'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(12), nullable=False)
    trade_date = Column(Date, nullable=False)

    # price & tech
    close = Column(Double, nullable=True)
    rps_250 = Column(Double, nullable=True)
    rps_120 = Column(Double, nullable=True)
    rps_20 = Column(Double, nullable=True)
    rps_slope = Column(Double, nullable=True)
    ma20 = Column(Double, nullable=True)
    ma60 = Column(Double, nullable=True)
    ma250 = Column(Double, nullable=True)
    volume_ratio = Column(Double, nullable=True)
    rsi = Column(Double, nullable=True)
    macd_dif = Column(Double, nullable=True)
    macd_dea = Column(Double, nullable=True)

    # relative to entry
    pct_since_add = Column(Double, nullable=True)
    rps_change = Column(Double, nullable=True)

    # signals JSON array string
    signals = Column(Text, nullable=True)
    alert_level = Column(
        Enum('red', 'yellow', 'green', 'info', name='candidate_alert_level'),
        nullable=False, default='info',
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def signals_list(self) -> list:
        if not self.signals:
            return []
        try:
            return json.loads(self.signals)
        except Exception:
            return []

    def __repr__(self):
        return f'<CandidateMonitorDaily code={self.stock_code} date={self.trade_date}>'
