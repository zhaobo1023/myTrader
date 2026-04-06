# -*- coding: utf-8 -*-
"""
Skill Auth Router - Device Flow endpoints for Claude skill authentication.

Three endpoints:
  POST /api/skill/auth/device/code    - Generate a short-lived device code
  POST /api/skill/auth/device/token   - Poll until code is verified, then issue tokens
  POST /api/skill/auth/device/verify  - Logged-in user confirms the device code
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_redis, get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.core.security import create_access_token, create_refresh_token
from api.services.device_auth import DeviceAuthService
from api.config import settings

router = APIRouter(prefix="/api/skill/auth", tags=["skill-auth"])


class DeviceTokenRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^[A-Z0-9]+$")


@router.post("/device/code")
async def create_device_code(redis: aioredis.Redis = Depends(get_redis)):
    """Generate a short-lived device code for skill authentication."""
    svc = DeviceAuthService(redis)
    result = await svc.create_code()
    return {
        **result,
        # /verify is a frontend page that POSTs to /api/skill/auth/device/verify
        "verify_url": f"{settings.api_base_url}/verify?code={result['code']}",
    }


@router.post("/device/token")
async def poll_device_token(
    req: DeviceTokenRequest,
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll for token after device code has been verified by the user.
    Returns status=pending if not yet verified, or access/refresh tokens when ready.
    Rate limited to 10 requests per minute per IP.
    """
    # Rate limit: 10 req/min per IP
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"skill:auth:poll_rate:{client_ip}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 60)
    if count > 10:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before polling again.")

    svc = DeviceAuthService(redis)
    user_id = await svc.poll_code(req.code)
    if user_id == "missing":
        raise HTTPException(
            status_code=400,
            detail={"status": "invalid_code", "message": "Code expired or not found"},
        )
    if user_id is None:
        return {"status": "pending"}

    # user_id is int, proceed to issue tokens
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="User not found or inactive")

    token_data = {"sub": str(user.id), "email": user.email, "tier": user.tier.value}
    return {
        "status": "ready",
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
    }


@router.post("/device/verify")
async def verify_device_code(
    req: DeviceTokenRequest,
    current_user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Browser endpoint: logged-in user confirms the device code."""
    svc = DeviceAuthService(redis)
    ok = await svc.verify_code(req.code, current_user.id)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    return {"status": "verified"}
