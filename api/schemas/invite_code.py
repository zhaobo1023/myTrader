# -*- coding: utf-8 -*-
"""
InviteCode schemas - request/response models
"""
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class InviteCodeCreate(BaseModel):
    count: int = Field(default=1, ge=1, le=50)
    max_uses: int = Field(default=1, ge=1, le=100)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class InviteCodeResponse(BaseModel):
    code: str
    max_uses: int
    use_count: int
    is_active: bool
    expires_at: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True
