# -*- coding: utf-8 -*-
"""
Health check router
"""
from fastapi import APIRouter

from api.config import settings
from api.dependencies import check_db_health, check_redis_health
from api.schemas.health import HealthResponse

router = APIRouter(tags=['system'])


@router.get('/health', response_model=HealthResponse)
async def health_check():
    """Health check endpoint - verifies DB and Redis connectivity"""
    db_ok, db_msg = await check_db_health()
    redis_ok, redis_msg = await check_redis_health()

    all_ok = db_ok and redis_ok
    return HealthResponse(
        status='ok' if all_ok else 'degraded',
        version=settings.app_version,
        db=db_msg,
        redis=redis_msg,
    )
