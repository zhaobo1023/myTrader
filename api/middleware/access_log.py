# -*- coding: utf-8 -*-
"""
Access log middleware.

Emits one log line per HTTP request to the 'myTrader.access' logger:

    GET /api/research/watchlist 200 45.3ms 127.0.0.1
"""
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

access_logger = logging.getLogger('myTrader.access')

# Paths that are too noisy to log (health checks, static assets)
_SKIP_PATHS = {'/health', '/metrics', '/favicon.ico', '/docs', '/redoc', '/openapi.json'}


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log one line per HTTP request with method, path, status, latency, IP."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000

        client_ip = _get_ip(request)
        msg = (
            f'{request.method} {request.url.path} '
            f'{response.status_code} '
            f'{latency_ms:.1f}ms '
            f'{client_ip}'
        )
        # Use WARNING for 5xx so errors are visible even at WARNING level
        if response.status_code >= 500:
            access_logger.warning(msg)
        else:
            access_logger.info(msg)

        return response


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'
