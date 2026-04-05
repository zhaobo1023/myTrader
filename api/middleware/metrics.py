# -*- coding: utf-8 -*-
"""
Prometheus metrics middleware for FastAPI
"""
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger('myTrader.api')

# Simple in-process metrics (no prometheus_client dependency required)
_metrics: dict = {
    'request_count': 0,
    'request_errors': 0,
    'request_latency_ms': [],
    'requests_by_path': {},
    'requests_by_status': {},
}

MAX_LATENCY_SAMPLES = 1000


def get_metrics() -> dict:
    """Return current metrics snapshot."""
    latencies = _metrics['request_latency_ms']
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p95_idx = int(len(latencies) * 0.95) if latencies else 0
    p95_latency = sorted(latencies)[p95_idx] if latencies else 0

    return {
        'request_count': _metrics['request_count'],
        'request_errors': _metrics['request_errors'],
        'avg_latency_ms': round(avg_latency, 2),
        'p95_latency_ms': round(p95_latency, 2),
        'requests_by_path': dict(_metrics['requests_by_path']),
        'requests_by_status': dict(_metrics['requests_by_status']),
    }


class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect request latency and status code metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        response = await call_next(request)
        latency_ms = (time.time() - start) * 1000

        path = request.url.path
        status = response.status_code

        _metrics['request_count'] += 1
        if status >= 400:
            _metrics['request_errors'] += 1

        # Track latency
        latencies = _metrics['request_latency_ms']
        latencies.append(latency_ms)
        if len(latencies) > MAX_LATENCY_SAMPLES:
            _metrics['request_latency_ms'] = latencies[-MAX_LATENCY_SAMPLES:]

        # Track by path
        path_key = path
        _metrics['requests_by_path'][path_key] = _metrics['requests_by_path'].get(path_key, 0) + 1

        # Track by status
        status_key = str(status)
        _metrics['requests_by_status'][status_key] = _metrics['requests_by_status'].get(status_key, 0) + 1

        # Add timing header for debugging
        response.headers['X-Response-Time'] = f'{latency_ms:.1f}ms'

        return response
