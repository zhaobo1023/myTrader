# -*- coding: utf-8 -*-
"""
Auth middleware - [AUTH-DISABLED] all endpoints open, no JWT check.

To re-enable authentication, restore the original get_current_user that
validates HTTPBearer credentials and looks up the user in the database.
"""
from typing import Optional

from api.models.user import User


class _AnonUser:
    """Lightweight stand-in when no real user is available."""
    id = 0
    email = 'anonymous@localhost'
    tier = 'pro'
    role = 'admin'
    is_active = True


_ANON = _AnonUser()


async def get_current_user() -> User:
    """Return a fake admin user -- auth is disabled."""
    return _ANON  # type: ignore[return-value]


async def get_optional_user() -> Optional[User]:
    return _ANON  # type: ignore[return-value]


async def require_admin() -> User:
    return _ANON  # type: ignore[return-value]
