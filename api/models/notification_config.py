# api/models/notification_config.py
# -*- coding: utf-8 -*-
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from api.dependencies import Base


class UserNotificationConfig(Base):
    __tablename__ = 'user_notification_configs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)

    webhook_url: Mapped[str] = mapped_column(String(500), nullable=True)

    notify_on_red: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_yellow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_on_green: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    score_threshold: Mapped[float] = mapped_column(Float, nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
