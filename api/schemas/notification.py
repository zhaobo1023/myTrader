# api/schemas/notification.py
# -*- coding: utf-8 -*-
from typing import Optional
from pydantic import BaseModel


class NotificationConfigUpdate(BaseModel):
    webhook_url: Optional[str] = None
    notify_on_red: bool = True
    notify_on_yellow: bool = False
    notify_on_green: bool = False
    score_threshold: Optional[float] = None
    enabled: bool = True


class NotificationConfigResponse(BaseModel):
    webhook_url: Optional[str]
    notify_on_red: bool
    notify_on_yellow: bool
    notify_on_green: bool
    score_threshold: Optional[float]
    enabled: bool

    model_config = {'from_attributes': True}
