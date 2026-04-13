# -*- coding: utf-8 -*-
"""
Market Overview router - macro dashboard signals

GET /api/market-overview/summary    -- legacy 8-group signal summary, 6h Redis cache
GET /api/market-overview/dashboard  -- new 6-section market dashboard, 6h Redis cache
GET /api/market-overview/signal-log -- recent signal change log
"""
import json
import logging
from typing import Any, Dict

import anyio
from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from api.dependencies import get_redis

logger = logging.getLogger('myTrader.api')

router = APIRouter(prefix='/api/market-overview', tags=['market-overview'])

CACHE_KEY = 'market_overview:summary'
CACHE_TTL = 6 * 3600  # 6 hours

DASHBOARD_CACHE_KEY = 'market_overview:dashboard'
DASHBOARD_CACHE_TTL = 6 * 3600  # 6 hours


def _compute_sync() -> Dict[str, Any]:
    """Synchronous wrapper for import + compute to run in thread executor."""
    from data_analyst.market_overview.calculator import compute_all
    return compute_all()


def _compute_dashboard_sync() -> Dict[str, Any]:
    """Synchronous wrapper for dashboard computation."""
    from data_analyst.market_dashboard.calculator import compute_dashboard
    return compute_dashboard()


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


@router.get('/dashboard')
async def get_market_dashboard(
    redis: Redis = Depends(get_redis),
) -> Dict[str, Any]:
    """
    Return the 6-section market dashboard data.
    Sections: temperature, trend, sentiment, style, stock_bond, macro + signal_log.
    Cached in Redis for 6 hours.
    """
    # Try cache first
    try:
        cached = await redis.get(DASHBOARD_CACHE_KEY)
        if cached:
            return json.loads(cached)
    except Exception as exc:
        logger.warning('Redis get (dashboard) failed, computing fresh: %s', exc)

    # Compute in thread
    try:
        result = await anyio.to_thread.run_sync(_compute_dashboard_sync)
    except Exception as exc:
        logger.error('compute_dashboard failed: %s', exc)
        return {'error': str(exc), 'available': False}

    # Cache result
    try:
        await redis.setex(DASHBOARD_CACHE_KEY, DASHBOARD_CACHE_TTL, json.dumps(result, default=str))
    except Exception as exc:
        logger.warning('Redis setex (dashboard) failed: %s', exc)

    return result


@router.get('/signal-log')
async def get_signal_log(days: int = Query(default=7, ge=1, le=30)) -> list:
    """Return recent signal change log entries."""
    try:
        from data_analyst.market_dashboard.calculator import get_signal_log
        return await anyio.to_thread.run_sync(lambda: get_signal_log(days=days))
    except Exception as exc:
        logger.error('get_signal_log failed: %s', exc)
        return []


@router.delete('/cache')
async def invalidate_cache(redis: Redis = Depends(get_redis)) -> Dict[str, str]:
    """Manually invalidate both summary and dashboard caches (admin use)."""
    try:
        await redis.delete(CACHE_KEY)
        await redis.delete(DASHBOARD_CACHE_KEY)
        return {'status': 'ok', 'message': 'all caches cleared'}
    except Exception as exc:
        return {'status': 'error', 'message': str(exc)}
