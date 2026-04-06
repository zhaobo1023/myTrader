# -*- coding: utf-8 -*-
"""
Skill Gateway - /api/skill/v1/execute unified execution endpoint.
"""
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_redis
from api.middleware.auth import get_current_user
from api.models.user import User
from api.services.skill_permissions import PermissionDenied, SkillPermissions
from api.services.skill_actions import stock_query

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
    data = await handler(ctx)

    return {
        "skill_id": req.skill_id,
        "action": req.action,
        "version": req.version,
        "data": data,
        "meta": {"quota_used": None, "quota_remaining": None},
    }
