# -*- coding: utf-8 -*-
"""
tech_scan action handler - Run tech scan for a stock code with LLM quota enforcement.
"""
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.llm_quota import LLMQuotaService, QuotaExceeded  # noqa: F401
from api.models.user import User, UserRole


async def run(
    params: dict,
    db: AsyncSession,
    user: User,
    redis: aioredis.Redis,
) -> dict:
    """Run tech scan for a stock code. Consumes LLM quota.

    Raises:
        ValueError: if params.code is missing.
        QuotaExceeded: if user has exhausted monthly LLM quota.
    """
    code = params.get("code", "").strip()
    if not code:
        raise ValueError("params.code is required")

    # Admin bypasses quota check (-1 = unlimited)
    override_limit = -1 if user.role == UserRole.ADMIN else None

    quota_svc = LLMQuotaService(redis)
    await quota_svc.check_and_increment(
        user_id=user.id,
        tier=user.tier.value,
        override_limit=override_limit,
    )
    # ^ raises QuotaExceeded if over limit; caller (gateway) catches -> 429

    # Placeholder: actual tech scan would call strategist.tech_scan module
    return {
        "code": code,
        "status": "queued",
        "message": "Tech scan report will be generated. Check output/single_scan/ for results.",
    }
