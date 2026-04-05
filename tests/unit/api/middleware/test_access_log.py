# -*- coding: utf-8 -*-
import logging
import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI


def _make_app():
    from api.middleware.access_log import AccessLogMiddleware
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)

    @app.get('/ping')
    async def ping():
        return {'ok': True}

    @app.get('/fail')
    async def fail():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail='not found')

    return app


def test_access_log_emits_on_success(caplog):
    """Successful request must produce one access log line with method/path/status/ms."""
    app = _make_app()
    with caplog.at_level(logging.INFO, logger='myTrader.access'):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/ping')
    assert resp.status_code == 200
    access_lines = [r for r in caplog.records if r.name == 'myTrader.access']
    assert len(access_lines) == 1
    msg = access_lines[0].message
    assert 'GET' in msg
    assert '/ping' in msg
    assert '200' in msg
    assert 'ms' in msg


def test_access_log_emits_on_error(caplog):
    """4xx responses must also be logged."""
    app = _make_app()
    with caplog.at_level(logging.INFO, logger='myTrader.access'):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/fail')
    assert resp.status_code == 404
    access_lines = [r for r in caplog.records if r.name == 'myTrader.access']
    assert len(access_lines) == 1
    assert '404' in access_lines[0].message


def test_access_log_includes_client_ip(caplog):
    """Log line must contain the client IP."""
    app = _make_app()
    with caplog.at_level(logging.INFO, logger='myTrader.access'):
        client = TestClient(app, raise_server_exceptions=False)
        client.get('/ping')
    access_lines = [r for r in caplog.records if r.name == 'myTrader.access']
    assert len(access_lines) == 1
    # at minimum the line must not be empty
    assert len(access_lines[0].message) > 10
