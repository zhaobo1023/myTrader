# -*- coding: utf-8 -*-
"""
Quota middleware - daily usage tracking for free tier users
"""
import logging
from datetime import date

from fastapi import Request, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.models.usage_log import UsageLog
from api.models.user import UserTier

logger = logging.getLogger('myTrader.api')

# Daily quota per endpoint type for free tier
FREE_DAILY_QUOTA = {
    '/api/analysis': 10,
    '/api/backtest': 3,
    '/api/rag': 10,
}

# Endpoints that count against quota
QUOTA_ENDPOINTS = set(FREE_DAILY_QUOTA.keys())


async def check_quota(
    request: Request,
    redis: Redis,
    db: AsyncSession,
    user_id: int,
    user_tier: str,
):
    """
    Check daily usage quota for free tier users.

    Uses Redis for fast counting, with DB as source of truth.
    """
    # Pro users have no quota limits
    if user_tier == UserTier.PRO.value:
        return

    path = request.url.path

    # Check if this endpoint has a quota
    matched_endpoint = None
    for ep in QUOTA_ENDPOINTS:
        if path.startswith(ep):
            matched_endpoint = ep
            break

    if matched_endpoint is None:
        return

    daily_limit = FREE_DAILY_QUOTA.get(matched_endpoint, 100)

    # Try Redis first for fast check
    redis_key = f'quota:{user_id}:{matched_endpoint}:{date.today()}'
    try:
        current = await redis.incr(redis_key)
        if current == 1:
            await redis.expire(redis_key, 86400)  # 24h TTL

        if current > daily_limit:
            logger.info(
                '[QUOTA] User %d exceeded daily quota for %s (%d/%d)',
                user_id, matched_endpoint, current, daily_limit,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f'Daily quota exceeded for {matched_endpoint}. Limit: {daily_limit}/day',
            )

    except HTTPException:
        raise
    except Exception as e:
        # Fail-open on Redis error
        logger.error('[QUOTA] Redis error (fail-open): %s', e)


async def record_usage(
    db: AsyncSession,
    user_id: int,
    endpoint: str,
):
    """
    Record API usage in database (called after successful request).
    """
    matched_endpoint = None
    for ep in QUOTA_ENDPOINTS:
        if endpoint.startswith(ep):
            matched_endpoint = ep
            break

    if matched_endpoint is None:
        return

    # Upsert usage count for today
    result = await db.execute(
        select(UsageLog).where(
            UsageLog.user_id == user_id,
            UsageLog.api_endpoint == matched_endpoint,
            UsageLog.usage_date == date.today(),
        )
    )
    log_entry = result.scalar_one_or_none()

    if log_entry:
        log_entry.count += 1
    else:
        log_entry = UsageLog(
            user_id=user_id,
            api_endpoint=matched_endpoint,
            usage_date=date.today(),
            count=1,
        )
        db.add(log_entry)
