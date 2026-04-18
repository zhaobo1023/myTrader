# -*- coding: utf-8 -*-
"""
Auth schemas - request/response models for authentication
"""
import re
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

_PASSWORD_RE = re.compile(r'^(?=.*[a-zA-Z])(?=.*\d).{8,128}$')


def _validate_password_strength(v: str) -> str:
    if not _PASSWORD_RE.match(v):
        raise ValueError('Password must contain at least one letter and one digit')
    return v


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50, pattern=r'^[\w\u4e00-\u9fff]+$')
    password: str = Field(min_length=8, max_length=128)
    invite_code: str = Field(min_length=1, max_length=32)
    display_name: Optional[str] = Field(default=None, max_length=100)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


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
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator('new_password')
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


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
