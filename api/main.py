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
from api.middleware.access_log import AccessLogMiddleware
from api.middleware.metrics import MetricsMiddleware, get_metrics
from api.middleware.rate_limit import RateLimitMiddleware
from api.routers import health, auth, market, analysis, strategy, rag, portfolio, admin, api_keys, subscription, research
from api.routers.watchlist import router as watchlist_router
from api.routers.notification import router as notification_router
from api.routers.scan_results import router as scan_results_router
from api.routers.skill_auth import router as skill_auth_router
from api.routers.skill_gateway import router as skill_gw_router
from api.routers.market_overview import router as market_overview_router
from api.routers.sentiment import router as sentiment_router
from api.routers.sw_rotation import router as sw_rotation_router
from api.routers.portfolio_mgmt import router as portfolio_mgmt_router
from api.routers.theme_pool import router as theme_pool_router
from api.routers.candidate_pool import router as candidate_pool_router
from api.routers.sim_pool import router as sim_pool_router

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
# CORS - 限制允许的来源以防止 CSRF 攻击
# ============================================================
allow_origins = ['http://localhost:3000', 'http://127.0.0.1:3000', 'http://123.56.3.1']
if settings.api_debug:
    # 开发模式允许本地开发服务器
    allow_origins.extend(['http://localhost:3001', 'http://127.0.0.1:3001'])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
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
# Access Log Middleware
# ============================================================
# Added last so it runs outermost -- logs every request including
# those rejected by rate limiter or auth.
app.add_middleware(AccessLogMiddleware)

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
app.include_router(watchlist_router)
app.include_router(notification_router)
app.include_router(scan_results_router)
app.include_router(skill_auth_router)
app.include_router(skill_gw_router)
app.include_router(market_overview_router)
app.include_router(sentiment_router)
app.include_router(sw_rotation_router)
app.include_router(portfolio_mgmt_router)
app.include_router(theme_pool_router)
app.include_router(candidate_pool_router)
app.include_router(sim_pool_router)


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
