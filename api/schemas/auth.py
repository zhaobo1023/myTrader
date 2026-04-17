# -*- coding: utf-8 -*-
"""
Auth schemas - request/response models for authentication
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50, pattern=r'^[\w\u4e00-\u9fff]+$')
    password: str = Field(min_length=6, max_length=128)
    invite_code: str = Field(min_length=1, max_length=32)
    display_name: Optional[str] = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    tier: str
    role: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True
