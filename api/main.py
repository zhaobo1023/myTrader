# -*- coding: utf-8 -*-
"""
myTrader API - FastAPI Application

Main entry point with lifespan management for DB pool and Redis.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.dependencies import close_redis
from api.logging_config import setup_logging
from api.middleware.metrics import MetricsMiddleware, get_metrics
from api.middleware.rate_limit import RateLimitMiddleware
from api.routers import health, auth, market, analysis, strategy, rag, portfolio, admin, api_keys, subscription, research

logger = logging.getLogger('myTrader.api')

# ============================================================
# Logging -- must be configured before any logger is used
# ============================================================
setup_logging(log_level=settings.log_level, log_dir=settings.log_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events"""
    # ---- Startup ----
    logger.info('[STARTUP] myTrader API v%s', settings.app_version)
    logger.info('[STARTUP] DB env: %s', settings.db_env)
    logger.info('[STARTUP] Redis: %s:%s', settings.redis_host, settings.redis_port)

    # Validate settings
    errors = settings.validate_startup()
    if errors:
        for err in errors:
            logger.warning('[STARTUP] Config warning: %s', err)

    logger.info('[STARTUP] API ready')

    yield

    # ---- Shutdown ----
    logger.info('[SHUTDOWN] Closing Redis connection...')
    await close_redis()
    logger.info('[SHUTDOWN] Cleanup complete')


app = FastAPI(
    title=settings.app_name,
    description='myTrader personal quantitative trading platform API',
    version=settings.app_version,
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc',
)

# ============================================================
# CORS
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'] if settings.api_debug else [],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# ============================================================
# Metrics Middleware
# ============================================================
app.add_middleware(MetricsMiddleware)

# ============================================================
# Rate Limiting Middleware
# ============================================================
# Sliding-window Redis rate limiter. Runs after MetricsMiddleware.
# Fail-open: requests are allowed through if Redis is unavailable.
app.add_middleware(RateLimitMiddleware)

# ============================================================
# Routers
# ============================================================
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(market.router)
app.include_router(analysis.router)
app.include_router(strategy.router)
app.include_router(rag.router)
app.include_router(portfolio.router)
app.include_router(admin.router)
app.include_router(api_keys.router)
app.include_router(subscription.router)
app.include_router(research.router)


@app.get('/')
async def root():
    return {
        'name': settings.app_name,
        'version': settings.app_version,
        'docs': '/docs',
    }


@app.get('/metrics')
async def metrics():
    """Application metrics endpoint."""
    return get_metrics()
