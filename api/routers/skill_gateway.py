# -*- coding: utf-8 -*-
"""
Skill Gateway - /api/skill/v1/execute unified execution endpoint.
"""
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_redis
from api.middleware.auth import get_current_user
from api.models.user import User, UserRole
from api.services.llm_quota import LLMQuotaService, QuotaExceeded
from api.services.skill_permissions import PermissionDenied, SkillPermissions
from api.services.skill_actions import stock_query, tech_scan

router = APIRouter(prefix="/api/skill", tags=["skill-gateway"])


@dataclass
class ExecuteContext:
    params: dict
    db: AsyncSession
    user: User
    redis: aioredis.Redis


# Registry: (skill_id, action) -> handler(ctx) -> dict
_ACTION_HANDLERS: dict[tuple[str, str], Any] = {
    ("stock-query", "search"): lambda ctx: stock_query.search(ctx.params, ctx.db),
    ("tech-scan", "run"): lambda ctx: tech_scan.run(ctx.params, ctx.db, ctx.user, ctx.redis),
}


class ExecuteRequest(BaseModel):
    skill_id: str
    action: str
    version: int = 1
    params: dict[str, Any] = {}


@router.post("/v1/execute")
async def execute_v1(
    req: ExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    try:
        SkillPermissions.check(current_user, req.skill_id, req.action)
    except PermissionDenied as e:
        raise HTTPException(403, str(e))

    handler = _ACTION_HANDLERS.get((req.skill_id, req.action))
    if handler is None:
        raise HTTPException(404, f"No handler for {req.skill_id}:{req.action}")

    ctx = ExecuteContext(params=req.params, db=db, user=current_user, redis=redis)
    try:
        data = await handler(ctx)
    except QuotaExceeded as e:
        return JSONResponse(
            status_code=429,
            content={
                "error": "quota_exceeded",
                "detail": str(e),
                "reset_at": e.reset_at,
            },
        )

    quota_svc = LLMQuotaService(redis)
    effective_tier = current_user.tier.value
    quota_status = await quota_svc.get_status(current_user.id, effective_tier)
    if current_user.role == UserRole.ADMIN:
        quota_status = {"used": quota_status["used"], "limit": -1, "remaining": -1}

    return {
        "skill_id": req.skill_id,
        "action": req.action,
        "version": req.version,
        "data": data,
        "meta": {
            "quota_used": quota_status["used"],
            "quota_remaining": quota_status["remaining"],
        },
    }
