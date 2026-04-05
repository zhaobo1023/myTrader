# -*- coding: utf-8 -*-
"""
Dependency injection for FastAPI

Provides reusable dependencies:
- Database session (async SQLAlchemy)
- Redis client
- Settings
"""
from typing import AsyncGenerator, Optional, Tuple

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
import redis.asyncio as aioredis

from api.config import settings


# ============================================================
# SQLAlchemy Async Engine
# ============================================================

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
    echo=settings.api_debug,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy ORM base class for API models"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async DB session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================
# Redis Client
# ============================================================

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency: yield a Redis client"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
        )
    return _redis_client


async def close_redis():
    """Close Redis connection on shutdown"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


# ============================================================
# Health check helpers
# ============================================================

async def check_db_health() -> Tuple[bool, str]:
    """Check database connectivity"""
    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            result.scalar()
        return True, "ok"
    except Exception as e:
        return False, str(e)[:100]


async def check_redis_health() -> Tuple[bool, str]:
    """Check Redis connectivity"""
    try:
        r = await get_redis()
        await r.ping()
        return True, "ok"
    except Exception as e:
        return False, str(e)[:100]
