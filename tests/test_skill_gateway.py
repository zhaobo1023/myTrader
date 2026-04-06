# -*- coding: utf-8 -*-
"""
Tests for /api/skill/v1/execute gateway endpoint.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from api.main import app
from api.middleware.auth import get_current_user
from api.models.user import User, UserTier, UserRole


def make_mock_user(tier: UserTier, role: UserRole = UserRole.USER) -> User:
    u = MagicMock(spec=User)
    u.id = 1
    u.email = "test@example.com"
    u.tier = tier
    u.role = role
    u.is_active = True
    return u


@pytest.mark.asyncio
async def test_execute_v1_requires_auth():
    """No token -> 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/skill/v1/execute", json={
            "skill_id": "stock-query", "action": "search",
            "version": 1, "params": {"query": "平安"}
        })
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_execute_v1_free_user_stock_query():
    """Free user can call stock-query:search."""
    free_user = make_mock_user(UserTier.FREE)
    mock_search = AsyncMock(return_value={"stocks": [{"code": "000001.SZ", "close": 12.5}]})

    app.dependency_overrides[get_current_user] = lambda: free_user
    try:
        import api.services.skill_actions.stock_query as sq_module
        original_search = sq_module.search
        sq_module.search = mock_search

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/skill/v1/execute",
                headers={"Authorization": "Bearer fake-token"},
                json={"skill_id": "stock-query", "action": "search",
                      "version": 1, "params": {"query": "平安"}}
            )
    finally:
        app.dependency_overrides.clear()
        sq_module.search = original_search

    assert resp.status_code == 200
    body = resp.json()
    assert body["skill_id"] == "stock-query"
    assert body["action"] == "search"
    assert "data" in body
    assert "meta" in body


@pytest.mark.asyncio
async def test_execute_v1_free_user_denied_pro_skill():
    """Free user cannot call tech-scan:run -> 403."""
    free_user = make_mock_user(UserTier.FREE)

    app.dependency_overrides[get_current_user] = lambda: free_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/skill/v1/execute",
                headers={"Authorization": "Bearer fake-token"},
                json={"skill_id": "tech-scan", "action": "run",
                      "version": 1, "params": {"code": "000001"}}
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_execute_v1_unknown_skill_returns_404():
    """Unknown skill -> 403 (PermissionDenied for unknown) or 404."""
    pro_user = make_mock_user(UserTier.PRO)

    app.dependency_overrides[get_current_user] = lambda: pro_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/skill/v1/execute",
                headers={"Authorization": "Bearer fake-token"},
                json={"skill_id": "nonexistent", "action": "run",
                      "version": 1, "params": {}}
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code in (403, 404)
