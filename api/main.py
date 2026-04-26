# -*- coding: utf-8 -*-
"""
myTrader API - FastAPI Application

Main entry point with lifespan management for DB pool and Redis.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.dependencies import close_redis
from api.logging_config import setup_logging
from api.middleware.access_log import AccessLogMiddleware
from api.middleware.auth import require_admin
from api.middleware.metrics import MetricsMiddleware, get_metrics
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.routers import health, auth, market, analysis, strategy, rag, portfolio, admin, api_keys, subscription, research
from api.routers.documents import router as documents_router
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
from api.routers.positions import router as positions_router
from api.routers.risk import router as risk_router
from api.routers.inbox import router as inbox_router
from api.routers.agent import router as agent_router
from api.routers.trade_operation_log import router as trade_log_router
from api.routers.chart import router as chart_router
from api.routers.wechat_feed import router as wechat_feed_router

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
    docs_url='/docs' if settings.api_debug else None,
    redoc_url='/redoc' if settings.api_debug else None,
    openapi_url='/openapi.json' if settings.api_debug else None,
)

# ============================================================
# CORS - 限制允许的来源以防止 CSRF 攻击
# ============================================================
allow_origins = ['http://localhost:3000', 'http://127.0.0.1:3000', 'https://mytrader.cc', 'https://www.mytrader.cc']
if settings.cors_extra_origins:
    allow_origins.extend(
        o.strip() for o in settings.cors_extra_origins.split(',') if o.strip()
    )
if settings.api_debug:
    allow_origins.extend(['http://localhost:3001', 'http://127.0.0.1:3001'])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'Authorization', 'Accept', 'X-API-Key'],
)

# ============================================================
# Security Headers Middleware
# ============================================================
app.add_middleware(SecurityHeadersMiddleware)

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
app.include_router(positions_router)
app.include_router(risk_router)
app.include_router(inbox_router)
app.include_router(documents_router)
app.include_router(agent_router)
app.include_router(trade_log_router)
app.include_router(chart_router)
app.include_router(wechat_feed_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error('[unhandled] %s %s -> %s', request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get('/')
async def root():
    info = {
        'name': settings.app_name,
        'version': settings.app_version,
    }
    if settings.api_debug:
        info['docs'] = '/docs'
    return info


@app.get('/metrics')
async def metrics(_admin=Depends(require_admin)):
    """Application metrics endpoint (admin only)."""
    return get_metrics()
