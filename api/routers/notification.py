# api/routers/notification.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.models.notification_config import UserNotificationConfig
from api.schemas.notification import NotificationConfigUpdate, NotificationConfigResponse

router = APIRouter(prefix='/api/notification', tags=['notification'])

_DEFAULT_CONFIG = NotificationConfigResponse(
    webhook_url=None,
    notify_on_red=True,
    notify_on_yellow=False,
    notify_on_green=False,
    score_threshold=None,
    enabled=True,
)


@router.get('/config', response_model=NotificationConfigResponse)
async def get_notification_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get notification config; returns defaults if not set"""
    result = await db.execute(
        select(UserNotificationConfig).where(UserNotificationConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        return _DEFAULT_CONFIG
    return NotificationConfigResponse.model_validate(config)


@router.put('/config', response_model=NotificationConfigResponse)
async def update_notification_config(
    req: NotificationConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update notification config (upsert)"""
    result = await db.execute(
        select(UserNotificationConfig).where(UserNotificationConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        config = UserNotificationConfig(user_id=current_user.id)
        db.add(config)

    config.webhook_url = req.webhook_url
    config.notify_on_red = req.notify_on_red
    config.notify_on_yellow = req.notify_on_yellow
    config.notify_on_green = req.notify_on_green
    config.score_threshold = req.score_threshold
    config.enabled = req.enabled

    await db.flush()
    await db.refresh(config)
    return NotificationConfigResponse.model_validate(config)
