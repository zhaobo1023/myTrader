# Skill Gateway Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Claude Code Skill 提供带鉴权、RBAC、LLM 配额、版本路由的统一网关，支持非技术用户通过短码登录。

**Architecture:** Device Flow 短码登录（Redis 存储验证码状态）→ JWT 复用现有体系 → RBAC 基于 users.tier + skill_permissions 配置 → LLM 配额用 Redis 计数 + usage_logs 落库 → 版本路由通过路径前缀 `/api/skill/v{n}/` 实现，v1 永久保留。

**Tech Stack:** FastAPI, SQLAlchemy (aiomysql), Redis (aioredis), python-jose JWT, Pydantic, Alembic, pytest-asyncio

---

## Phase 1: 短码登录 + Skill 鉴权流程

### Task 1: 在 Redis 中设计 Device Code 数据结构

**Context:**
- Redis client 已在 `api/dependencies.py` 的 `get_redis()` 中初始化，`decode_responses=True`
- 无需新建数据库表，全部用 Redis TTL 管理生命周期
- Key 格式：`skill:device:{code}` → JSON string `{"user_id": null, "created_at": "..."}`
- TTL: 300 秒（5 分钟）

**Files:**
- Create: `api/services/device_auth.py`
- Create: `tests/test_device_auth.py`

**Step 1: 写失败测试**

```python
# tests/test_device_auth.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from api.services.device_auth import DeviceAuthService

@pytest.mark.asyncio
async def test_create_device_code_returns_6_char_code():
    redis = AsyncMock()
    redis.setex = AsyncMock()
    svc = DeviceAuthService(redis)
    result = await svc.create_code()
    assert len(result["code"]) == 6
    assert result["code"].isupper()
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
```

**Step 2: 运行确认失败**

```bash
cd /Users/zhaobo/data0/person/myTrader
python -m pytest tests/test_device_auth.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'DeviceAuthService'`

**Step 3: 实现 DeviceAuthService**

```python
# api/services/device_auth.py
import json
import random
import string
from datetime import datetime
import redis.asyncio as aioredis

CODE_TTL = 300  # seconds
CODE_PREFIX = "skill:device:"


class DeviceAuthService:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _make_code(self) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    async def create_code(self) -> dict:
        code = self._make_code()
        payload = json.dumps({"user_id": None, "created_at": datetime.utcnow().isoformat()})
        await self.redis.setex(f"{CODE_PREFIX}{code}", CODE_TTL, payload)
        return {"code": code, "expires_in": CODE_TTL}

    async def poll_code(self, code: str):
        """Return user_id if verified, None if pending or expired."""
        raw = await self.redis.get(f"{CODE_PREFIX}{code}")
        if raw is None:
            return None
        data = json.loads(raw)
        return data.get("user_id")  # None = still pending

    async def verify_code(self, code: str, user_id: int) -> bool:
        """Called after user authenticates in browser. Marks code as verified."""
        key = f"{CODE_PREFIX}{code}"
        raw = await self.redis.get(key)
        if raw is None:
            return False
        data = json.loads(raw)
        if data["user_id"] is not None:
            return False  # already used
        data["user_id"] = user_id
        ttl = await self.redis.ttl(key)
        await self.redis.setex(key, max(ttl, 1), json.dumps(data))
        return True
```

**Step 4: 跑测试**

```bash
python -m pytest tests/test_device_auth.py -v
```
Expected: 4 passed

**Step 5: Commit**

```bash
git add api/services/device_auth.py tests/test_device_auth.py
git commit -m "feat(skill-gw): add DeviceAuthService for short-code device flow"
```

---

### Task 2: Device Flow API 端点

**Context:**
- `POST /api/skill/auth/device/code` — 生成短码，返回 `{code, verify_url, expires_in}`
- `POST /api/skill/auth/device/token` — Skill 轮询用，返回 `{status: pending|ready, access_token?, refresh_token?}`
- `POST /api/skill/auth/device/verify` — 用户在浏览器点击确认，需要已登录（JWT）

**Files:**
- Create: `api/routers/skill_auth.py`
- Modify: `api/main.py` (include router)

**Step 1: 写失败测试**

```python
# tests/test_skill_auth_router.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
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
        assert body["expires_in"] == 300

@pytest.mark.asyncio
async def test_poll_token_returns_pending_when_not_verified():
    with patch("api.routers.skill_auth.DeviceAuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.poll_code = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/skill/auth/device/token", json={"code": "ABC123"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

@pytest.mark.asyncio
async def test_poll_token_returns_tokens_when_verified(test_user):
    with patch("api.routers.skill_auth.DeviceAuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.poll_code = AsyncMock(return_value=test_user.id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/skill/auth/device/token", json={"code": "ABC123"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert "access_token" in body
        assert "refresh_token" in body
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_skill_auth_router.py -v 2>&1 | head -20
```

**Step 3: 实现路由**

```python
# api/routers/skill_auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_redis, get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.core.security import create_access_token, create_refresh_token
from api.services.device_auth import DeviceAuthService
from api.config import settings

router = APIRouter(prefix="/api/skill/auth", tags=["skill-auth"])


class DeviceTokenRequest(BaseModel):
    code: str


@router.post("/device/code")
async def create_device_code(redis: aioredis.Redis = Depends(get_redis)):
    svc = DeviceAuthService(redis)
    result = await svc.create_code()
    return {
        **result,
        "verify_url": f"{settings.api_base_url}/skill/verify?code={result['code']}",
    }


@router.post("/device/token")
async def poll_device_token(
    req: DeviceTokenRequest,
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    svc = DeviceAuthService(redis)
    user_id = await svc.poll_code(req.code)
    if user_id is None:
        return {"status": "pending"}

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(400, "User not found or inactive")

    token_data = {"sub": str(user.id), "email": user.email, "tier": user.tier.value}
    return {
        "status": "ready",
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
    }


@router.post("/device/verify")
async def verify_device_code(
    req: DeviceTokenRequest,
    current_user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Browser endpoint: logged-in user confirms the device code."""
    svc = DeviceAuthService(redis)
    ok = await svc.verify_code(req.code, current_user.id)
    if not ok:
        raise HTTPException(400, "Invalid or expired code")
    return {"status": "verified"}
```

**Step 4: 在 config.py 添加 `api_base_url`**

```python
# api/config.py — 在 Settings 类中添加
api_base_url: str = "http://localhost:8000"
```
.env 中对应加：`API_BASE_URL=https://your-domain.com`

**Step 5: 在 main.py 注册路由**

```python
# api/main.py — 在已有 include_router 处添加
from api.routers.skill_auth import router as skill_auth_router
app.include_router(skill_auth_router)
```

**Step 6: 跑测试**

```bash
python -m pytest tests/test_skill_auth_router.py -v
```

**Step 7: Commit**

```bash
git add api/routers/skill_auth.py api/services/device_auth.py api/config.py api/main.py tests/test_skill_auth_router.py
git commit -m "feat(skill-gw): add device flow endpoints (create/poll/verify)"
```

---

### Task 3: Skill 登录引导 SKILL.md

**Context:**
- 这是一个独立 Skill，用于首次设置 token
- Token 存到 `~/.config/myskills/token`（chmod 600）
- 成功后告知用户 "登录成功，后续操作会自动使用此 token"

**Files:**
- Create: `~/.claude/skills/mytrader-login/SKILL.md`（或 `/Users/zhaobo/data0/person/mySkills/mytrader-login/SKILL.md`）

**Step 1: 创建 Skill 文件**

```markdown
---
name: mytrader-login
description: 登录 myTrader 服务，获取访问 token。首次使用或 token 过期时调用。
---

# myTrader 登录

## 流程

1. 调用 `POST {API_BASE_URL}/api/skill/auth/device/code`
   - 获取 `{code, verify_url, expires_in}`

2. 告知用户：
   "请在浏览器打开以下链接完成登录（5分钟内有效）：
   {verify_url}
   或手动前往 {API_BASE_URL}/skill/verify 输入验证码：**{code}**"

3. 每 3 秒轮询一次 `POST {API_BASE_URL}/api/skill/auth/device/token` 
   Body: `{"code": "{code}"}`
   - `status == "pending"` → 继续等待，最多轮询 100 次（5分钟）
   - `status == "ready"` → 进入步骤 4
   - 超时 → 告知用户"登录超时，请重新尝试"，终止

4. 将 token 写入本地文件：
   ```bash
   mkdir -p ~/.config/myskills
   echo '{access_token}' > ~/.config/myskills/token
   chmod 600 ~/.config/myskills/token
   ```

5. 告知用户："登录成功！后续操作将自动使用此 token，无需重复登录。"

## 触发条件
- 用户说"登录"、"login"、"授权"、"初始化 myTrader"
- 其他 myTrader Skill 发现 `~/.config/myskills/token` 不存在时引导调用此 Skill
```

**Step 2: Commit**

```bash
git add docs/plans/2026-04-06-skill-gateway.md
git commit -m "docs: add skill gateway implementation plan"
```

---

## Phase 2: RBAC + 第一个受保护的 Skill Action

### Task 4: Skill 权限配置表

**Context:**
- 不新建 DB 表，用 Python dict 配置（便于版本控制，变更可见）
- `user.tier` (free/pro) + `user.role` (user/admin) 决定权限
- Skill 权限格式：`skill_id:action`，例如 `stock-query:search`

**Files:**
- Create: `api/services/skill_permissions.py`
- Create: `tests/test_skill_permissions.py`

**Step 1: 写失败测试**

```python
# tests/test_skill_permissions.py
import pytest
from api.services.skill_permissions import SkillPermissions, PermissionDenied
from api.models.user import User, UserTier, UserRole

def make_user(tier: UserTier, role: UserRole = UserRole.USER) -> User:
    u = User()
    u.tier = tier
    u.role = role
    return u

def test_free_user_can_access_free_skill():
    user = make_user(UserTier.FREE)
    SkillPermissions.check(user, "stock-query", "search")  # should not raise

def test_free_user_cannot_access_pro_skill():
    user = make_user(UserTier.FREE)
    with pytest.raises(PermissionDenied):
        SkillPermissions.check(user, "tech-scan", "run")

def test_pro_user_can_access_all_skills():
    user = make_user(UserTier.PRO)
    SkillPermissions.check(user, "tech-scan", "run")  # should not raise
    SkillPermissions.check(user, "stock-query", "search")  # should not raise

def test_admin_bypasses_all_checks():
    user = make_user(UserTier.FREE, UserRole.ADMIN)
    SkillPermissions.check(user, "tech-scan", "run")  # admin bypasses tier

def test_unknown_skill_raises_permission_denied():
    user = make_user(UserTier.PRO)
    with pytest.raises(PermissionDenied):
        SkillPermissions.check(user, "nonexistent-skill", "run")
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_skill_permissions.py -v 2>&1 | head -10
```

**Step 3: 实现 SkillPermissions**

```python
# api/services/skill_permissions.py
from api.models.user import User, UserTier, UserRole

class PermissionDenied(Exception):
    pass

# skill_id -> {action -> min_tier}
SKILL_ACL: dict[str, dict[str, str]] = {
    "stock-query": {
        "search": "free",
    },
    "market-overview": {
        "daily": "free",
    },
    "tech-scan": {
        "run": "pro",
    },
    "fundamental-report": {
        "generate": "pro",
    },
}

_TIER_RANK = {UserTier.FREE: 0, UserTier.PRO: 1}
_TIER_BY_STR = {"free": UserTier.FREE, "pro": UserTier.PRO}


class SkillPermissions:
    @staticmethod
    def check(user: User, skill_id: str, action: str) -> None:
        if user.role == UserRole.ADMIN:
            return
        if skill_id not in SKILL_ACL:
            raise PermissionDenied(f"Unknown skill: {skill_id}")
        actions = SKILL_ACL[skill_id]
        if action not in actions:
            raise PermissionDenied(f"Unknown action '{action}' for skill '{skill_id}'")
        required_str = actions[action]
        required = _TIER_BY_STR[required_str]
        if _TIER_RANK[user.tier] < _TIER_RANK[required]:
            raise PermissionDenied(
                f"Skill '{skill_id}:{action}' requires tier '{required_str}', "
                f"user has '{user.tier.value}'"
            )
```

**Step 4: 跑测试**

```bash
python -m pytest tests/test_skill_permissions.py -v
```

**Step 5: Commit**

```bash
git add api/services/skill_permissions.py tests/test_skill_permissions.py
git commit -m "feat(skill-gw): add SkillPermissions RBAC config"
```

---

### Task 5: 第一个 Skill Action — stock-query/search

**Context:**
- `POST /api/skill/v1/execute` — 统一执行入口
- Request: `{skill_id, action, version, params}`
- Response: `{skill_id, action, version, data, meta: {used_quota, remaining_quota}}`
- 先实现 `stock-query:search`，从 `trade_stock_daily` 查最新行情
- JWT Auth via `get_current_user`，RBAC via `SkillPermissions.check`

**Files:**
- Create: `api/routers/skill_gateway.py`
- Create: `api/services/skill_actions/stock_query.py`
- Create: `tests/test_skill_gateway.py`
- Modify: `api/main.py`

**Step 1: 写失败测试**

```python
# tests/test_skill_gateway.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from api.main import app

@pytest.mark.asyncio
async def test_execute_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/skill/v1/execute", json={
            "skill_id": "stock-query", "action": "search",
            "version": 1, "params": {"query": "平安"}
        })
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_execute_free_user_stock_query(free_user_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/skill/v1/execute",
            headers={"Authorization": f"Bearer {free_user_token}"},
            json={"skill_id": "stock-query", "action": "search",
                  "version": 1, "params": {"query": "平安"}}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["skill_id"] == "stock-query"
    assert "data" in body
    assert "meta" in body

@pytest.mark.asyncio
async def test_execute_free_user_denied_pro_skill(free_user_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/skill/v1/execute",
            headers={"Authorization": f"Bearer {free_user_token}"},
            json={"skill_id": "tech-scan", "action": "run",
                  "version": 1, "params": {"code": "000001"}}
        )
    assert resp.status_code == 403
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_skill_gateway.py::test_execute_requires_auth -v
```

**Step 3: 实现 stock-query action**

```python
# api/services/skill_actions/stock_query.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def search(params: dict, db: AsyncSession) -> dict:
    query_str = params.get("query", "").strip()
    limit = min(int(params.get("limit", 10)), 50)
    if not query_str:
        return {"stocks": []}
    sql = text("""
        SELECT ts_code, trade_date, open, high, low, close, vol, amount
        FROM trade_stock_daily
        WHERE ts_code LIKE :q
        ORDER BY trade_date DESC
        LIMIT :limit
    """)
    result = await db.execute(sql, {"q": f"%{query_str}%", "limit": limit})
    rows = result.fetchall()
    return {
        "stocks": [
            {"code": r.ts_code, "date": str(r.trade_date),
             "open": float(r.open or 0), "high": float(r.high or 0),
             "low": float(r.low or 0), "close": float(r.close or 0),
             "vol": float(r.vol or 0)}
            for r in rows
        ]
    }
```

**Step 4: 实现 Gateway Router**

```python
# api/routers/skill_gateway.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.services.skill_permissions import SkillPermissions, PermissionDenied
from api.services.skill_actions import stock_query

router = APIRouter(prefix="/api/skill", tags=["skill-gateway"])

_ACTION_HANDLERS = {
    ("stock-query", "search"): stock_query.search,
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
):
    try:
        SkillPermissions.check(current_user, req.skill_id, req.action)
    except PermissionDenied as e:
        raise HTTPException(403, str(e))

    handler = _ACTION_HANDLERS.get((req.skill_id, req.action))
    if handler is None:
        raise HTTPException(404, f"No handler for {req.skill_id}:{req.action}")

    data = await handler(req.params, db)
    return {
        "skill_id": req.skill_id,
        "action": req.action,
        "version": req.version,
        "data": data,
        "meta": {"quota_used": None, "quota_remaining": None},  # Phase 3 填充
    }
```

**Step 5: 注册路由到 main.py**

```python
from api.routers.skill_gateway import router as skill_gw_router
app.include_router(skill_gw_router)
```

也需要创建 `api/services/skill_actions/__init__.py`（空文件）。

**Step 6: 跑测试**

```bash
python -m pytest tests/test_skill_gateway.py -v
```

**Step 7: Commit**

```bash
git add api/routers/skill_gateway.py api/services/skill_actions/ tests/test_skill_gateway.py api/main.py
git commit -m "feat(skill-gw): add /api/skill/v1/execute with RBAC and stock-query action"
```

---

## Phase 3: LLM 成本控制

### Task 6: Redis 配额计数 + UsageLog 落库

**Context:**
- Redis key: `skill:quota:llm:{user_id}:{YYYY-MM}` → integer，TTL 设为当月剩余秒数
- 配额上限来自 `SkillPermissions` 里的 tier 配置（新增 `llm_quota` 字段）
- 超配时返回 HTTP 429，body 包含 `{error: "quota_exceeded", reset_at: "2026-05-01"}`
- 每次 LLM 调用后往 `usage_logs` 插入一条（`api_endpoint='/api/skill/llm'`，`count+=1`）

**Files:**
- Create: `api/services/llm_quota.py`
- Modify: `api/services/skill_permissions.py`（新增 llm_quota 配置）
- Create: `tests/test_llm_quota.py`

**Step 1: 更新 SKILL_ACL，加入 llm_quota**

在 `api/services/skill_permissions.py` 中，在文件顶部添加：

```python
# tier -> monthly LLM call quota (-1 = unlimited)
TIER_LLM_QUOTA: dict[str, int] = {
    "free": 0,
    "pro": 100,
    "admin": -1,
}
```

**Step 2: 写失败测试**

```python
# tests/test_llm_quota.py
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from api.services.llm_quota import LLMQuotaService, QuotaExceeded

@pytest.mark.asyncio
async def test_check_quota_passes_for_pro_user_under_limit():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="5")
    svc = LLMQuotaService(redis)
    await svc.check_and_increment(user_id=1, tier="pro")  # 5 < 100, should not raise

@pytest.mark.asyncio
async def test_check_quota_raises_for_free_user():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="0")
    svc = LLMQuotaService(redis)
    with pytest.raises(QuotaExceeded):
        await svc.check_and_increment(user_id=1, tier="free")

@pytest.mark.asyncio
async def test_check_quota_raises_when_pro_limit_reached():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="100")
    svc = LLMQuotaService(redis)
    with pytest.raises(QuotaExceeded):
        await svc.check_and_increment(user_id=1, tier="pro")

@pytest.mark.asyncio
async def test_admin_tier_never_raises():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="99999")
    svc = LLMQuotaService(redis)
    await svc.check_and_increment(user_id=1, tier="admin")  # -1 = unlimited

@pytest.mark.asyncio
async def test_increment_sets_key_with_ttl_on_first_call():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # first call this month
    redis.incr = AsyncMock(return_value=1)
    redis.expireat = AsyncMock()
    svc = LLMQuotaService(redis)
    await svc.check_and_increment(user_id=1, tier="pro")
    redis.incr.assert_called_once()
    redis.expireat.assert_called_once()
```

**Step 3: 运行确认失败**

```bash
python -m pytest tests/test_llm_quota.py -v 2>&1 | head -10
```

**Step 4: 实现 LLMQuotaService**

```python
# api/services/llm_quota.py
import calendar
from datetime import date
import redis.asyncio as aioredis
from api.services.skill_permissions import TIER_LLM_QUOTA

QUOTA_KEY_PREFIX = "skill:quota:llm:"


class QuotaExceeded(Exception):
    def __init__(self, tier: str, limit: int, reset_at: str):
        self.tier = tier
        self.limit = limit
        self.reset_at = reset_at
        super().__init__(f"LLM quota exceeded: {limit}/month for tier '{tier}'")


class LLMQuotaService:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _key(self, user_id: int) -> str:
        ym = date.today().strftime("%Y-%m")
        return f"{QUOTA_KEY_PREFIX}{user_id}:{ym}"

    def _month_end_timestamp(self) -> int:
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        return int(date(today.year, today.month, last_day).strftime("%s")) + 86400

    def _reset_at(self) -> str:
        today = date.today()
        if today.month == 12:
            return f"{today.year + 1}-01-01"
        return f"{today.year}-{today.month + 1:02d}-01"

    async def check_and_increment(self, user_id: int, tier: str) -> int:
        limit = TIER_LLM_QUOTA.get(tier, 0)
        if limit == -1:
            return -1  # unlimited, skip Redis

        key = self._key(user_id)
        raw = await self.redis.get(key)
        used = int(raw) if raw else 0

        if used >= limit:
            raise QuotaExceeded(tier=tier, limit=limit, reset_at=self._reset_at())

        new_val = await self.redis.incr(key)
        if new_val == 1:  # first increment this month, set TTL
            await self.redis.expireat(key, self._month_end_timestamp())
        return new_val

    async def get_status(self, user_id: int, tier: str) -> dict:
        limit = TIER_LLM_QUOTA.get(tier, 0)
        if limit == -1:
            return {"used": 0, "limit": -1, "remaining": -1}
        raw = await self.redis.get(self._key(user_id))
        used = int(raw) if raw else 0
        return {"used": used, "limit": limit, "remaining": max(0, limit - used)}
```

**Step 5: 将配额状态注入 execute 响应的 meta**

在 `api/routers/skill_gateway.py` 中更新 `execute_v1`：

```python
# 在 execute_v1 末尾，replace "meta": {...}
from api.services.llm_quota import LLMQuotaService
import redis.asyncio as aioredis
from api.dependencies import get_redis

# 在函数签名中加 redis: aioredis.Redis = Depends(get_redis)
quota_svc = LLMQuotaService(redis)
quota_status = await quota_svc.get_status(current_user.id, current_user.tier.value)
return {
    ...
    "meta": {
        "quota_used": quota_status["used"],
        "quota_remaining": quota_status["remaining"],
    },
}
```

**Step 6: 跑测试**

```bash
python -m pytest tests/test_llm_quota.py -v
python -m pytest tests/test_skill_gateway.py -v
```

**Step 7: Commit**

```bash
git add api/services/llm_quota.py api/services/skill_permissions.py api/routers/skill_gateway.py tests/test_llm_quota.py
git commit -m "feat(skill-gw): add LLM quota service with Redis counting and tier limits"
```

---

### Task 7: LLM 调用拦截点（示范用 tech-scan action）

**Context:**
- 以 `tech-scan:run` 为例，演示 LLM 调用如何经过配额检查
- 实际 LLM 调用可以是 `investment_rag` 模块里的任意调用
- 配额检查失败时返回标准 429 响应

**Files:**
- Create: `api/services/skill_actions/tech_scan.py`
- Modify: `api/routers/skill_gateway.py`

**Step 1: 实现 tech_scan action（含配额扣减）**

```python
# api/services/skill_actions/tech_scan.py
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from api.services.llm_quota import LLMQuotaService, QuotaExceeded

async def run(params: dict, db: AsyncSession, user_id: int, tier: str, redis: aioredis.Redis) -> dict:
    code = params.get("code", "").strip()
    if not code:
        raise ValueError("params.code is required")

    quota_svc = LLMQuotaService(redis)
    await quota_svc.check_and_increment(user_id=user_id, tier=tier)
    # ^ raises QuotaExceeded if over limit

    # 实际调用 tech_scan 或 LLM（此处为占位）
    return {"code": code, "status": "report_generated", "report_url": f"/output/{code}.html"}
```

**Step 2: 在 gateway router 中处理 QuotaExceeded**

```python
# api/routers/skill_gateway.py — 在 execute_v1 中添加 try/except
from api.services.llm_quota import QuotaExceeded
from fastapi.responses import JSONResponse

# 在 handler 调用前后：
try:
    data = await handler(req.params, db)  # tech_scan.run 需要额外参数，见下方
except QuotaExceeded as e:
    return JSONResponse(
        status_code=429,
        content={"error": "quota_exceeded", "detail": str(e), "reset_at": e.reset_at}
    )
```

注意：tech_scan.run 需要 `user_id`, `tier`, `redis` 参数，gateway 需要统一传入这些上下文。可以将 handler 签名改为接受 `ExecuteContext`：

```python
# api/routers/skill_gateway.py 内定义
from dataclasses import dataclass

@dataclass
class ExecuteContext:
    params: dict
    db: AsyncSession
    user: User
    redis: aioredis.Redis
```

所有 handler 统一改为 `async def handler(ctx: ExecuteContext) -> dict`，方便后续扩展。

**Step 3: 写测试**

```python
# tests/test_skill_gateway.py — 新增
@pytest.mark.asyncio
async def test_execute_returns_429_when_quota_exceeded(pro_user_token):
    with patch("api.routers.skill_gateway.LLMQuotaService") as MockQuota:
        instance = MockQuota.return_value
        from api.services.llm_quota import QuotaExceeded
        instance.check_and_increment = AsyncMock(
            side_effect=QuotaExceeded("pro", 100, "2026-05-01")
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/skill/v1/execute",
                headers={"Authorization": f"Bearer {pro_user_token}"},
                json={"skill_id": "tech-scan", "action": "run",
                      "version": 1, "params": {"code": "000001"}}
            )
    assert resp.status_code == 429
    assert resp.json()["error"] == "quota_exceeded"
```

**Step 4: 跑测试**

```bash
python -m pytest tests/test_skill_gateway.py -v
```

**Step 5: Commit**

```bash
git add api/services/skill_actions/tech_scan.py api/routers/skill_gateway.py tests/test_skill_gateway.py
git commit -m "feat(skill-gw): add tech-scan action with LLM quota enforcement and 429 response"
```

---

## Phase 4: API 版本化路由

### Task 8: v1/v2 路由分离 + 向前兼容

**Context:**
- 现有 `/api/skill/v1/execute` 永久保留，不做破坏性改动
- v2 在 v1 基础上扩展响应格式，加入 `warnings` 字段（用于"Skill 版本过旧"提示）
- 通过请求头 `X-Skill-Version` 允许同一端点感知客户端版本
- 版本路由逻辑抽象到 `api/services/skill_router.py`，保持 gateway router 干净

**Files:**
- Create: `api/services/skill_router.py`
- Modify: `api/routers/skill_gateway.py`（新增 v2 端点）
- Create: `tests/test_skill_versioning.py`

**Step 1: 写失败测试**

```python
# tests/test_skill_versioning.py
import pytest
from api.services.skill_router import SkillRouter, VersionWarning

def test_v1_request_no_warnings():
    router = SkillRouter(current_version=2)
    warnings = router.get_warnings(client_version=1, skill_id="stock-query")
    assert any("outdated" in w.lower() for w in warnings)  # soft warning

def test_v2_request_no_warnings():
    router = SkillRouter(current_version=2)
    warnings = router.get_warnings(client_version=2, skill_id="stock-query")
    assert warnings == []

def test_unknown_client_version_gets_warning():
    router = SkillRouter(current_version=2)
    warnings = router.get_warnings(client_version=0, skill_id="stock-query")
    assert len(warnings) > 0
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_skill_versioning.py -v 2>&1 | head -10
```

**Step 3: 实现 SkillRouter**

```python
# api/services/skill_router.py

CURRENT_GATEWAY_VERSION = 2
MIN_SUPPORTED_VERSION = 1


class VersionWarning:
    pass  # marker


class SkillRouter:
    def __init__(self, current_version: int = CURRENT_GATEWAY_VERSION):
        self.current_version = current_version

    def get_warnings(self, client_version: int, skill_id: str) -> list[str]:
        warnings = []
        if client_version < MIN_SUPPORTED_VERSION:
            warnings.append(
                f"Skill version {client_version} is no longer supported. "
                f"Minimum: {MIN_SUPPORTED_VERSION}"
            )
        elif client_version < self.current_version:
            warnings.append(
                f"Skill version {client_version} is outdated. "
                f"Latest: {self.current_version}. Some features may be unavailable."
            )
        return warnings

    def is_supported(self, client_version: int) -> bool:
        return client_version >= MIN_SUPPORTED_VERSION
```

**Step 4: 在 gateway router 新增 v2 端点**

```python
# api/routers/skill_gateway.py — 新增
from fastapi import Header
from api.services.skill_router import SkillRouter

_skill_router = SkillRouter()


@router.post("/v2/execute")
async def execute_v2(
    req: ExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    x_skill_version: int = Header(default=2, alias="X-Skill-Version"),
):
    # 检查版本兼容性
    warnings = _skill_router.get_warnings(x_skill_version, req.skill_id)

    # 复用 v1 核心逻辑
    v1_result = await _execute_core(req, current_user, db, redis)

    # v2 在 v1 基础上扩展 warnings
    return {**v1_result, "warnings": warnings}


async def _execute_core(req: ExecuteRequest, user: User, db: AsyncSession, redis: aioredis.Redis) -> dict:
    """Shared execution logic for v1 and v2."""
    try:
        SkillPermissions.check(user, req.skill_id, req.action)
    except PermissionDenied as e:
        raise HTTPException(403, str(e))

    handler = _ACTION_HANDLERS.get((req.skill_id, req.action))
    if handler is None:
        raise HTTPException(404, f"No handler for {req.skill_id}:{req.action}")

    ctx = ExecuteContext(params=req.params, db=db, user=user, redis=redis)
    try:
        data = await handler(ctx)
    except QuotaExceeded as e:
        raise HTTPException(429, {"error": "quota_exceeded", "detail": str(e), "reset_at": e.reset_at})

    quota_svc = LLMQuotaService(redis)
    quota_status = await quota_svc.get_status(user.id, user.tier.value)
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


# 重构 v1 使用 _execute_core
@router.post("/v1/execute")
async def execute_v1(
    req: ExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await _execute_core(req, current_user, db, redis)
```

**Step 5: 写版本化测试**

```python
# tests/test_skill_versioning.py — 新增集成测试
@pytest.mark.asyncio
async def test_v2_execute_includes_warnings_for_old_skill(pro_user_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/skill/v2/execute",
            headers={
                "Authorization": f"Bearer {pro_user_token}",
                "X-Skill-Version": "1",
            },
            json={"skill_id": "stock-query", "action": "search",
                  "version": 1, "params": {"query": "平安"}}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "warnings" in body
    assert len(body["warnings"]) > 0

@pytest.mark.asyncio
async def test_v1_endpoint_still_works(pro_user_token):
    """v1 must remain functional indefinitely."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/skill/v1/execute",
            headers={"Authorization": f"Bearer {pro_user_token}"},
            json={"skill_id": "stock-query", "action": "search",
                  "version": 1, "params": {"query": "平安"}}
        )
    assert resp.status_code == 200
    assert "warnings" not in resp.json()  # v1 never returns warnings
```

**Step 6: 跑所有测试**

```bash
python -m pytest tests/test_device_auth.py tests/test_skill_auth_router.py tests/test_skill_permissions.py tests/test_skill_gateway.py tests/test_llm_quota.py tests/test_skill_versioning.py -v
```
Expected: all green

**Step 7: 最终 Commit**

```bash
git add api/services/skill_router.py api/routers/skill_gateway.py tests/test_skill_versioning.py
git commit -m "feat(skill-gw): add v2 versioned endpoint with backward-compat warnings"
```

---

## 快速验证清单

```bash
# 1. 启动服务
make api-local

# 2. 生成短码
curl -X POST http://localhost:8000/api/skill/auth/device/code

# 3. 模拟浏览器确认（用已登录的 JWT）
curl -X POST http://localhost:8000/api/skill/auth/device/verify \
  -H "Authorization: Bearer <JWT>" \
  -d '{"code": "ABC123"}'

# 4. Skill 侧轮询
curl -X POST http://localhost:8000/api/skill/auth/device/token \
  -d '{"code": "ABC123"}'
# 期望: {"status": "ready", "access_token": "..."}

# 5. 执行 skill action（免费用户）
curl -X POST http://localhost:8000/api/skill/v1/execute \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -d '{"skill_id": "stock-query", "action": "search", "version": 1, "params": {"query": "平安"}}'

# 6. 验证 v1 和 v2 同时可用
curl -X POST http://localhost:8000/api/skill/v2/execute \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "X-Skill-Version: 1" \
  -d '{"skill_id": "stock-query", "action": "search", "version": 1, "params": {"query": "平安"}}'
# 期望：响应包含 "warnings": ["Skill version 1 is outdated..."]
```

---

## 文件清单

| 新建/修改 | 路径 |
|----------|------|
| 新建 | `api/services/device_auth.py` |
| 新建 | `api/services/skill_permissions.py` |
| 新建 | `api/services/llm_quota.py` |
| 新建 | `api/services/skill_router.py` |
| 新建 | `api/services/skill_actions/__init__.py` |
| 新建 | `api/services/skill_actions/stock_query.py` |
| 新建 | `api/services/skill_actions/tech_scan.py` |
| 新建 | `api/routers/skill_auth.py` |
| 新建 | `api/routers/skill_gateway.py` |
| 新建 | `tests/test_device_auth.py` |
| 新建 | `tests/test_skill_auth_router.py` |
| 新建 | `tests/test_skill_permissions.py` |
| 新建 | `tests/test_skill_gateway.py` |
| 新建 | `tests/test_llm_quota.py` |
| 新建 | `tests/test_skill_versioning.py` |
| 修改 | `api/main.py`（注册2个新 router）|
| 修改 | `api/config.py`（添加 `api_base_url`）|
| 新建 Skill | `mySkills/mytrader-login/SKILL.md` |
