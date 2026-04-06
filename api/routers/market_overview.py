# -*- coding: utf-8 -*-
"""
Market Overview router - macro dashboard signals

GET /api/market-overview/summary  -- returns all signal groups, 6h Redis cache
"""
import json
import logging
from typing import Any, Dict

import anyio
from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from api.dependencies import get_redis

logger = logging.getLogger('myTrader.api')

router = APIRouter(prefix='/api/market-overview', tags=['market-overview'])

CACHE_KEY = 'market_overview:summary'
CACHE_TTL = 6 * 3600  # 6 hours


def _compute_sync() -> Dict[str, Any]:
    """Synchronous wrapper for import + compute to run in thread executor."""
    from data_analyst.market_overview.calculator import compute_all
    return compute_all()


@router.get('/summary')
async def get_market_overview_summary(
    redis: Redis = Depends(get_redis),
) -> Dict[str, Any]:
    """
    Return all market overview signal groups.
    Data is cached in Redis for 6 hours after first computation.
    Computation runs in a thread pool to avoid blocking the event loop.
    """
    # Try cache first
    try:
        cached = await redis.get(CACHE_KEY)
        if cached:
            return json.loads(cached)
    except Exception as exc:
        logger.warning('Redis get failed, computing fresh: %s', exc)

    # Compute in thread (compute_all uses sync DB calls)
    try:
        result = await anyio.to_thread.run_sync(_compute_sync)
    except Exception as exc:
        logger.error('market_overview compute_all failed: %s', exc)
        return {'error': str(exc), 'available': False}

    # Cache result
    try:
        await redis.setex(CACHE_KEY, CACHE_TTL, json.dumps(result, default=str))
    except Exception as exc:
        logger.warning('Redis setex failed: %s', exc)

    return result


@router.delete('/cache')
async def invalidate_cache(redis: Redis = Depends(get_redis)) -> Dict[str, str]:
    """Manually invalidate the market overview cache (admin use)."""
    try:
        await redis.delete(CACHE_KEY)
        return {'status': 'ok', 'message': 'cache cleared'}
    except Exception as exc:
        return {'status': 'error', 'message': str(exc)}
