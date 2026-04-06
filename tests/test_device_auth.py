import pytest
import json
import re
from unittest.mock import AsyncMock
from api.services.device_auth import DeviceAuthService

@pytest.mark.asyncio
async def test_create_device_code_returns_6_char_code():
    redis = AsyncMock()
    redis.setex = AsyncMock()
    svc = DeviceAuthService(redis)
    result = await svc.create_code()
    assert re.fullmatch(r"[A-Z0-9]{6}", result["code"]) is not None
    assert result["expires_in"] == 300

@pytest.mark.asyncio
async def test_poll_code_returns_none_when_pending():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps({"user_id": None, "created_at": "2026-04-06T00:00:00"}))
    svc = DeviceAuthService(redis)
    result = await svc.poll_code("ABC123")
    assert result is None

@pytest.mark.asyncio
async def test_poll_code_returns_user_id_when_verified():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps({"user_id": 42, "created_at": "2026-04-06T00:00:00"}))
    svc = DeviceAuthService(redis)
    result = await svc.poll_code("ABC123")
    assert result == 42

@pytest.mark.asyncio
async def test_poll_code_returns_none_when_expired():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    svc = DeviceAuthService(redis)
    result = await svc.poll_code("ZZZZZZ")
    assert result is None

@pytest.mark.asyncio
async def test_verify_code_returns_true_on_success():
    redis = AsyncMock()
    redis.eval = AsyncMock(return_value=1)
    svc = DeviceAuthService(redis)
    result = await svc.verify_code("ABC123", 42)
    assert result is True
    redis.eval.assert_called_once()

@pytest.mark.asyncio
async def test_verify_code_returns_false_when_expired():
    redis = AsyncMock()
    redis.eval = AsyncMock(return_value=0)
    svc = DeviceAuthService(redis)
    result = await svc.verify_code("XXXXXX", 42)
    assert result is False

@pytest.mark.asyncio
async def test_verify_code_returns_false_when_already_used():
    redis = AsyncMock()
    redis.eval = AsyncMock(return_value=0)
    svc = DeviceAuthService(redis)
    result = await svc.verify_code("ABC123", 99)
    assert result is False
