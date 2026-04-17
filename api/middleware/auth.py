# -*- coding: utf-8 -*-
"""
Auth middleware - JWT bearer token validation + user lookup.

Set AUTH_ENABLED=false in .env to bypass auth (returns mock admin user).
"""
import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.user import User, UserRole
from api.core.security import decode_token

_bearer_scheme = HTTPBearer(auto_error=False)
_bearer_scheme_optional = HTTPBearer(auto_error=False)

AUTH_ENABLED = os.getenv('AUTH_ENABLED', 'true').lower() in ('true', '1', 'yes')


class _MockUser:
    """Lightweight mock user when auth is disabled. Avoids SQLAlchemy instrumentation."""
    id = 1
    username = 'admin'
    display_name = 'Admin'
    email = None
    role = UserRole.ADMIN
    tier = 'PRO'
    is_active = True


def _mock_admin_user():
    """Return a mock admin user when auth is disabled."""
    return _MockUser()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate JWT and return the authenticated user. Raises 401 on failure."""
    if not AUTH_ENABLED:
        return _mock_admin_user()

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Not authenticated',
        )
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get('type') != 'access':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired token',
        )
    try:
        user_id = int(payload['sub'])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid token payload',
        )
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='User not found or inactive',
        )
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Return the authenticated user if a valid token is present, else None."""
    if not AUTH_ENABLED:
        return _mock_admin_user()
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get('type') != 'access':
        return None
    try:
        user_id = int(payload['sub'])
    except (KeyError, ValueError):
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the authenticated user to have admin role."""
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    if role_value != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Admin access required',
        )
    return current_user
