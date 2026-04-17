# api/models/notification_config.py
# -*- coding: utf-8 -*-
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Integer, String, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from api.dependencies import Base


class UserNotificationConfig(Base):
    __tablename__ = 'user_notification_configs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)

    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    notify_on_red: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_yellow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_on_green: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    score_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Daily report preferences
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    daily_report_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_report_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True, default='17:00')
    report_include_watchlist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    report_include_positions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
