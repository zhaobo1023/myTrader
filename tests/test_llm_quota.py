import pytest
from unittest.mock import AsyncMock
from api.services.llm_quota import LLMQuotaService, QuotaExceeded
from api.models.user import UserTier


@pytest.mark.asyncio
async def test_check_passes_for_pro_user_under_limit():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="5")
    redis.incr = AsyncMock(return_value=6)
    redis.expireat = AsyncMock()
    svc = LLMQuotaService(redis)
    result = await svc.check_and_increment(user_id=1, tier=UserTier.PRO.value)
    assert result == 6  # new count after increment


@pytest.mark.asyncio
async def test_check_raises_for_free_tier():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="0")
    svc = LLMQuotaService(redis)
    with pytest.raises(QuotaExceeded) as exc_info:
        await svc.check_and_increment(user_id=1, tier=UserTier.FREE.value)
    assert exc_info.value.limit == 0
    assert exc_info.value.reset_at  # non-empty string


@pytest.mark.asyncio
async def test_check_raises_when_pro_limit_reached():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="100")
    svc = LLMQuotaService(redis)
    with pytest.raises(QuotaExceeded):
        await svc.check_and_increment(user_id=1, tier=UserTier.PRO.value)


@pytest.mark.asyncio
async def test_admin_tier_uses_role_bypass_not_quota():
    """admin tier value not in TIER_LLM_QUOTA; callers pass role separately."""
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=1)
    redis.expireat = AsyncMock()
    svc = LLMQuotaService(redis)
    # Pass unlimited=-1 directly (caller determined admin role)
    result = await svc.check_and_increment(user_id=1, tier=UserTier.PRO.value, override_limit=-1)
    assert result == 1  # incremented, no quota check


@pytest.mark.asyncio
async def test_first_increment_sets_expireat():
    """First call this month should set TTL to end of month."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # first call
    redis.incr = AsyncMock(return_value=1)
    redis.expireat = AsyncMock()
    svc = LLMQuotaService(redis)
    await svc.check_and_increment(user_id=1, tier=UserTier.PRO.value)
    redis.expireat.assert_called_once()
    # TTL target should be a future timestamp
    call_args = redis.expireat.call_args
    timestamp = call_args[0][1]
    import time
    assert timestamp > time.time()


@pytest.mark.asyncio
async def test_get_status_returns_used_remaining_limit():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="30")
    svc = LLMQuotaService(redis)
    status = await svc.get_status(user_id=1, tier=UserTier.PRO.value)
    assert status["used"] == 30
    assert status["limit"] == 100
    assert status["remaining"] == 70
