# api/models/scan_result.py
# -*- coding: utf-8 -*-
import json
from datetime import date, datetime
from sqlalchemy import Integer, String, Date, DateTime, Float, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from api.dependencies import Base


class UserScanResult(Base):
    __tablename__ = 'user_scan_results'
    __table_args__ = (
        Index('ix_scan_user_date', 'user_id', 'scan_date'),
        UniqueConstraint('user_id', 'stock_code', 'scan_date', name='uq_user_stock_date'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, default='')
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)

    score: Mapped[float] = mapped_column(Float, nullable=True)
    score_label: Mapped[str] = mapped_column(String(20), nullable=True)

    # JSON strings
    dimension_scores: Mapped[str] = mapped_column(Text, nullable=True)
    signals: Mapped[str] = mapped_column(Text, nullable=True)

    max_severity: Mapped[str] = mapped_column(String(10), nullable=False, default='NONE')
    notified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def get_signals(self) -> list:
        return json.loads(self.signals) if self.signals else []

    def get_dimension_scores(self) -> dict:
        return json.loads(self.dimension_scores) if self.dimension_scores else {}
