# -*- coding: utf-8 -*-
"""
Auth router - registration (invite code), login (username), token refresh, profile
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from api.dependencies import get_db
from api.models.user import User, UserTier, UserRole
from api.models.invite_code import InviteCode
from api.middleware.auth import get_current_user
from api.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from api.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    UpdateProfileRequest,
    ChangePasswordRequest,
    UserResponse,
)

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/auth', tags=['auth'])


@router.post('/register', response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register with username + password + invite code."""
    # Validate invite code
    result = await db.execute(
        select(InviteCode).where(InviteCode.code == req.invite_code)
    )
    invite = result.scalar_one_or_none()
    if not invite or not invite.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invalid invitation code',
        )
    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invitation code has expired',
        )
    if invite.use_count >= invite.max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invitation code has been fully used',
        )

    # Atomically consume invite code to prevent race condition:
    # UPDATE ... WHERE use_count < max_uses ensures only max_uses registrations succeed.
    consume_result = await db.execute(
        update(InviteCode)
        .where(
            InviteCode.id == invite.id,
            InviteCode.use_count < InviteCode.max_uses,
        )
        .values(use_count=InviteCode.use_count + 1)
    )
    if consume_result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invitation code has been fully used',
        )

    # Check if username already exists
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Username already taken',
        )

    # Create user
    user = User(
        username=req.username,
        display_name=req.display_name,
        hashed_password=hash_password(req.password),
        tier=UserTier.FREE,
        role=UserRole.USER,
        invited_by=invite.created_by,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Track who used the invite (for single-use codes)
    if invite.max_uses == 1:
        await db.execute(
            update(InviteCode)
            .where(InviteCode.id == invite.id)
            .values(used_by=user.id)
        )

    # Issue tokens
    token_data = {'sub': str(user.id), 'username': user.username, 'tier': user.tier.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.info('[AUTH] New user registered: id=%s username=%s', user.id, user.username)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post('/login', response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with username and password."""
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid username or password',
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Account is disabled',
        )

    token_data = {'sub': str(user.id), 'username': user.username, 'tier': user.tier.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.info('[AUTH] User logged in: id=%s username=%s', user.id, user.username)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post('/refresh', response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token."""
    payload = decode_token(req.refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired refresh token',
        )

    if payload.get('type') != 'refresh':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid token type',
        )

    # Re-validate user from DB: ensure still exists and active
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

    # Use fresh data from DB, not stale JWT payload
    token_data = {
        'sub': str(user.id),
        'username': user.username,
        'tier': user.tier.value if hasattr(user.tier, 'value') else str(user.tier),
    }
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.get('/me', response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return _user_to_response(current_user)


@router.put('/me', response_model=UserResponse)
async def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile (display_name, email)."""
    if req.display_name is not None:
        current_user.display_name = req.display_name

    if req.email is not None:
        # Check email uniqueness
        result = await db.execute(
            select(User).where(User.email == req.email, User.id != current_user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Email already in use',
            )
        current_user.email = req.email

    return _user_to_response(current_user)


@router.post('/change-password')
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """Change current user password."""
    if not verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Current password is incorrect',
        )
    current_user.hashed_password = hash_password(req.new_password)
    return {'message': 'Password changed successfully'}


def _user_to_response(user: User) -> UserResponse:
    """Convert User ORM object to response schema."""
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        tier=user.tier.value if hasattr(user.tier, 'value') else str(user.tier),
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else '',
    )
