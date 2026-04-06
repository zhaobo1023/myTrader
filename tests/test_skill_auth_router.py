# -*- coding: utf-8 -*-
"""
Tests for skill auth device flow endpoints.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock
from api.main import app


@pytest.mark.asyncio
async def test_create_device_code_returns_code_and_url():
    with patch("api.routers.skill_auth.DeviceAuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.create_code = AsyncMock(return_value={"code": "ABC123", "expires_in": 300})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/skill/auth/device/code")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "ABC123"
        assert "verify_url" in body
        assert "ABC123" in body["verify_url"]
        assert body["expires_in"] == 300


@pytest.mark.asyncio
async def test_poll_token_returns_pending_when_not_verified():
    with patch("api.routers.skill_auth.DeviceAuthService") as MockSvc:
        with patch("api.routers.skill_auth.aioredis") as mock_aioredis:
            instance = MockSvc.return_value
            instance.poll_code = AsyncMock(return_value=None)

            mock_redis = AsyncMock()
            mock_redis.incr = AsyncMock(return_value=1)
            mock_redis.expire = AsyncMock()

            from api.dependencies import get_redis
            async def override_get_redis():
                return mock_redis

            app.dependency_overrides[get_redis] = override_get_redis
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    resp = await ac.post("/api/skill/auth/device/token", json={"code": "ABC123"})
            finally:
                app.dependency_overrides.pop(get_redis, None)

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_poll_token_returns_400_when_code_missing():
    """poll_code returns 'missing' -> 400 with invalid_code status."""
    with patch("api.routers.skill_auth.DeviceAuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.poll_code = AsyncMock(return_value="missing")

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()

        from api.dependencies import get_redis
        async def override_get_redis():
            return mock_redis

        app.dependency_overrides[get_redis] = override_get_redis
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/api/skill/auth/device/token", json={"code": "XXXXXX"})
        finally:
            app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["status"] == "invalid_code"


@pytest.mark.asyncio
async def test_poll_token_rate_limited():
    """11th request from same IP should return 429."""
    mock_redis = AsyncMock()
    # First call returns 11 (already over the limit)
    mock_redis.incr = AsyncMock(return_value=11)
    mock_redis.expire = AsyncMock()

    from api.dependencies import get_redis
    async def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_redis] = override_get_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/skill/auth/device/token", json={"code": "ABC123"})
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_poll_token_returns_tokens_when_verified():
    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.email = "test@example.com"
    fake_user.tier = MagicMock()
    fake_user.tier.value = "free"
    fake_user.is_active = True

    async def mock_get(model, uid):
        return fake_user

    mock_db = AsyncMock()
    mock_db.get = mock_get

    async def override_get_db():
        yield mock_db

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    from api.dependencies import get_redis, get_db
    async def override_get_redis():
        return mock_redis

    with patch("api.routers.skill_auth.DeviceAuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.poll_code = AsyncMock(return_value=1)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/api/skill/auth/device/token", json={"code": "ABC123"})
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_verify_device_code_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/skill/auth/device/verify", json={"code": "ABC123"})
    assert resp.status_code == 403
