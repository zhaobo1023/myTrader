# -*- coding: utf-8 -*-
"""
Inbox schemas - request/response models
"""
from typing import Optional, List
from pydantic import BaseModel


class InboxMessageResponse(BaseModel):
    id: int
    message_type: str
    title: str
    content: Optional[str] = None
    metadata_json: Optional[str] = None
    is_read: bool
    created_at: str

    class Config:
        from_attributes = True


class InboxListResponse(BaseModel):
    items: List[InboxMessageResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int
