# -*- coding: utf-8 -*-
"""
Auth router - registration, login, token refresh, logout
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db
from api.models.user import User, UserTier, UserRole
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
    UserResponse,
)

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/auth', tags=['auth'])


@router.post('/register', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == req.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Email already registered',
        )

    # Create user
    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        tier=UserTier.FREE,
        role=UserRole.USER,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info('[AUTH] New user registered: id=%s email=%s', user.id, user.email)
    return _user_to_response(user)


@router.post('/login', response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email and password, returns JWT tokens."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid email or password',
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Account is disabled',
        )

    # Create tokens
    token_data = {'sub': str(user.id), 'email': user.email, 'tier': user.tier.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.info('[AUTH] User logged in: id=%s email=%s', user.id, user.email)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post('/refresh', response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
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

    # Create new access token
    token_data = {
        'sub': payload['sub'],
        'email': payload.get('email', ''),
        'tier': payload.get('tier', 'free'),
    }
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
    )


@router.get('/me', response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return _user_to_response(current_user)


def _user_to_response(user: User) -> UserResponse:
    """Convert User ORM object to response schema."""
    return UserResponse(
        id=user.id,
        email=user.email,
        tier=user.tier.value,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else '',
    )
