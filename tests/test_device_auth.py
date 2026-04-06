import pytest
import json
from unittest.mock import AsyncMock
from api.services.device_auth import DeviceAuthService

@pytest.mark.asyncio
async def test_create_device_code_returns_6_char_code():
    redis = AsyncMock()
    redis.setex = AsyncMock()
    svc = DeviceAuthService(redis)
    result = await svc.create_code()
    assert len(result["code"]) == 6
    assert result["code"].isupper() or result["code"].isalnum()
    assert "expires_in" in result
    assert result["expires_in"] == 300

@pytest.mark.asyncio
async def test_poll_code_returns_none_when_pending():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps({"user_id": None}))
    svc = DeviceAuthService(redis)
    result = await svc.poll_code("ABC123")
    assert result is None

@pytest.mark.asyncio
async def test_poll_code_returns_user_id_when_verified():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps({"user_id": 42}))
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
