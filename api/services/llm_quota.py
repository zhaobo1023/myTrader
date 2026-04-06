# -*- coding: utf-8 -*-
"""
LLMQuotaService - Redis-backed monthly LLM call quota management.

Redis key format: skill:quota:llm:{user_id}:{YYYY-MM}
TTL: expires at midnight UTC on the first day of the next month.
"""
from datetime import date, datetime, timezone

import redis.asyncio as aioredis

from api.services.skill_permissions import TIER_LLM_QUOTA

QUOTA_KEY_PREFIX = "skill:quota:llm:"

_INCR_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local expireat = tonumber(ARGV[2])
local new_val = redis.call('INCR', key)
if new_val == 1 then
    redis.call('EXPIREAT', key, expireat)
end
if limit >= 0 and new_val > limit then
    redis.call('DECR', key)
    return -1
end
return new_val
"""


class QuotaExceeded(Exception):
    def __init__(self, tier: str, limit: int, reset_at: str):
        self.tier = tier
        self.limit = limit
        self.reset_at = reset_at
        super().__init__(
            f"LLM quota exceeded: {limit}/month for tier '{tier}', resets {reset_at}"
        )


class LLMQuotaService:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _key(self, user_id: int) -> str:
        ym = date.today().strftime("%Y-%m")
        return f"{QUOTA_KEY_PREFIX}{user_id}:{ym}"

    def _month_end_timestamp(self) -> int:
        today = date.today()
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        # midnight UTC of the first day of next month
        dt = datetime(next_month.year, next_month.month, next_month.day, tzinfo=timezone.utc)
        return int(dt.timestamp())

    def _reset_at(self) -> str:
        today = date.today()
        if today.month == 12:
            return f"{today.year + 1}-01-01"
        return f"{today.year}-{today.month + 1:02d}-01"

    async def check_and_increment(
        self, user_id: int, tier: str, override_limit: int | None = None
    ) -> int:
        """Check quota and increment. Returns new count.

        Args:
            user_id: the user's database ID.
            tier: user tier string value (e.g. 'free', 'pro').
            override_limit: if -1, skip quota check (admin bypass).
        """
        limit = override_limit if override_limit is not None else TIER_LLM_QUOTA.get(tier, 0)

        key = self._key(user_id)

        if limit == -1:
            # Unlimited (admin override): just increment and set TTL on first use
            new_val = await self.redis.incr(key)
            if new_val == 1:
                await self.redis.expireat(key, self._month_end_timestamp())
            return new_val

        # Atomic INCR with limit check via Lua
        expireat = self._month_end_timestamp()
        result = await self.redis.eval(
            _INCR_LUA,
            1,
            key,
            str(limit),
            str(expireat),
        )
        if result == -1:
            used = await self.redis.get(key)
            raise QuotaExceeded(
                tier=tier,
                limit=limit,
                reset_at=self._reset_at(),
            )
        return result

    async def get_status(self, user_id: int, tier: str) -> dict:
        """Return quota status dict with used/limit/remaining."""
        limit = TIER_LLM_QUOTA.get(tier, 0)
        if limit == -1:
            return {"used": 0, "limit": -1, "remaining": -1}
        raw = await self.redis.get(self._key(user_id))
        used = int(raw) if raw is not None else 0
        return {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
        }
