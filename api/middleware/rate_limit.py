# -*- coding: utf-8 -*-
"""
Rate limiting middleware - Redis sliding window counter
"""
import time
import logging
from typing import Optional

from fastapi import Request, HTTPException, status
from redis.asyncio import Redis

logger = logging.getLogger('myTrader.api')

# Default rate limits per tier
RATE_LIMITS = {
    'free': {'requests': 60, 'window': 60},    # 60 req/min
    'pro': {'requests': 300, 'window': 60},     # 300 req/min
}

# Endpoints exempt from rate limiting
EXEMPT_PATHS = {'/health', '/docs', '/redoc', '/openapi.json'}


async def rate_limit_middleware(request: Request, redis: Redis, user_tier: str = 'free'):
    """
    Sliding window rate limiter using Redis.

    Args:
        request: FastAPI request
        redis: Redis client
        user_tier: user tier for determining limits

    Raises:
        HTTPException 429 if rate limit exceeded
    """
    path = request.url.path

    # Skip exempt paths
    if path in EXEMPT_PATHS:
        return

    # Get client identifier (user_id or IP)
    client_id = _get_client_id(request)

    # Get limit config
    limits = RATE_LIMITS.get(user_tier, RATE_LIMITS['free'])
    max_requests = limits['requests']
    window = limits['window']

    # Redis sliding window key
    key = f'rate_limit:{client_id}:{path}'
    now = time.time()
    window_start = now - window

    try:
        pipe = redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Count current window
        pipe.zcard(key)
        # Add current request
        pipe.zadd(key, {str(now): now})
        # Set expiry
        pipe.expire(key, window)

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= max_requests:
            logger.warning(
                '[RATE_LIMIT] Blocked: client=%s path=%s count=%d limit=%d',
                client_id, path, current_count, max_requests,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f'Rate limit exceeded: {max_requests} requests per {window}s',
                headers={'Retry-After': str(window)},
            )

    except HTTPException:
        raise
    except Exception as e:
        # Fail-open: if Redis is down, allow the request
        logger.error('[RATE_LIMIT] Redis error (fail-open): %s', e)


def _get_client_id(request: Request) -> str:
    """Extract client identifier from request."""
    # Prefer user_id from auth if available
    user = getattr(request.state, 'user', None)
    if user and hasattr(user, 'id'):
        return f'user:{user.id}'

    # Fall back to IP
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return f'ip:{forwarded.split(",")[0].strip()}'

    client_host = request.client.host if request.client else 'unknown'
    return f'ip:{client_host}'


def _extract_tier(request: Request) -> str:
    """
    Try to read user tier from JWT Authorization header.
    Returns 'free' on any failure (token missing, invalid, expired).
    """
    try:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return 'free'
        token = auth[7:]
        # Lazy import to avoid circular dependency; decode without full verification
        # (signature is verified by the auth middleware on protected routes).
        from api.config import settings
        try:
            from jose import jwt as jose_jwt
            payload = jose_jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm],
            )
        except ImportError:
            import jwt as pyjwt
            payload = pyjwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm],
            )
        return payload.get('tier', 'free')
    except Exception:
        return 'free'


class RateLimitMiddleware:
    """
    ASGI middleware that applies sliding-window rate limiting via Redis.

    Uses 'free' tier limits by default; upgrades to 'pro' limits if a valid
    JWT token with tier='pro' is present in the Authorization header.
    Fails open: if Redis is unavailable, all requests are allowed through.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            request = Request(scope, receive)
            try:
                from api.dependencies import get_redis
                redis = await get_redis()
                user_tier = _extract_tier(request)
                await rate_limit_middleware(request, redis, user_tier)
            except HTTPException as exc:
                from fastapi.responses import JSONResponse
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={'detail': exc.detail},
                    headers=dict(exc.headers) if exc.headers else {},
                )
                await response(scope, receive, send)
                return
            except Exception as e:
                logger.debug('[RATE_LIMIT] Middleware error (fail-open): %s', e)
        await self.app(scope, receive, send)
