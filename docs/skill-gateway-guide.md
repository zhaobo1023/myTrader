# Skill Gateway 使用指南

Skill Gateway 是 myTrader 的统一技能执行入口，允许 Claude Code Skill 和外部客户端通过鉴权、RBAC、LLM 配额管控后调用 myTrader 的数据和分析能力。

---

## 目录

- [架构概览](#架构概览)
- [认证流程：Device Flow 短码登录](#认证流程device-flow-短码登录)
- [执行技能：v1 / v2 端点](#执行技能v1--v2-端点)
- [权限与套餐](#权限与套餐)
- [LLM 配额](#llm-配额)
- [已支持的技能清单](#已支持的技能清单)
- [版本兼容](#版本兼容)
- [错误代码速查](#错误代码速查)
- [扩展：添加新技能](#扩展添加新技能)

---

## 架构概览

```
Claude Skill / 外部客户端
        |
        | 1. POST /api/skill/auth/device/code  -> 获取 6 位短码
        | 2. 用户在浏览器打开 /verify?code=XXXXXX 完成授权
        | 3. 客户端轮询 /api/skill/auth/device/token -> 拿到 JWT
        |
        | 4. POST /api/skill/v2/execute  (Bearer JWT)
        |
   Skill Gateway
        |---- RBAC 检查 (tier: free/pro, role: user/admin)
        |---- 分发到对应 action handler
        |---- LLM 配额计数 (Redis, 按月重置)
        |
   skill action (stock-query / tech-scan / ...)
```

---

## 认证流程：Device Flow 短码登录

适用于 Claude Code Skill 等无浏览器环境，或非技术用户只需扫码/点链接完成授权的场景。

### Step 1 - 申请短码

```bash
curl -X POST http://localhost:8000/api/skill/auth/device/code
```

响应：

```json
{
  "code": "A3Z9KQ",
  "expires_in": 300,
  "verify_url": "http://localhost:8000/verify?code=A3Z9KQ"
}
```

- `code`：6 位大写字母+数字，有效期 300 秒（5 分钟）
- `verify_url`：把这个 URL 发给用户，让用户在浏览器里打开并登录确认

### Step 2 - 用户在浏览器确认

已登录用户访问 `verify_url` 后，前端调用：

```bash
curl -X POST http://localhost:8000/api/skill/auth/device/verify \
  -H "Authorization: Bearer <user_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"code": "A3Z9KQ"}'
```

响应：

```json
{"status": "verified"}
```

### Step 3 - 客户端轮询获取 Token

用户确认前返回 `pending`，确认后返回 access/refresh token：

```bash
curl -X POST http://localhost:8000/api/skill/auth/device/token \
  -H "Content-Type: application/json" \
  -d '{"code": "A3Z9KQ"}'
```

**等待中：**

```json
{"status": "pending"}
```

**已就绪：**

```json
{
  "status": "ready",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

建议轮询间隔 2-5 秒，最多轮询到 code 过期（5 分钟）。轮询有频率限制：**每 IP 每分钟 10 次**，超出返回 429。

---

## 执行技能：v1 / v2 端点

拿到 token 后，通过统一的 `/execute` 端点调用任意已注册的技能 action。

### 请求格式

```bash
curl -X POST http://localhost:8000/api/skill/v2/execute \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -H "X-Skill-Version: 2" \
  -d '{
    "skill_id": "stock-query",
    "action": "search",
    "params": {"query": "600519", "limit": 5}
  }'
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `skill_id` | string | 是 | 技能标识，见[技能清单](#已支持的技能清单) |
| `action` | string | 是 | 技能下的具体操作 |
| `params` | object | 否 | 操作参数，默认 `{}` |

### 响应格式

```json
{
  "skill_id": "stock-query",
  "action": "search",
  "data": {
    "stocks": [
      {"code": "600519.SH", "date": "2026-04-04", "close": 1528.0, ...}
    ]
  },
  "meta": {
    "quota_used": 3,
    "quota_remaining": 97
  },
  "warnings": []
}
```

- `data`：技能返回的业务数据
- `meta.quota_used/remaining`：当月 LLM 调用配额使用情况
- `warnings`：版本警告（仅 v2 包含此字段）

### v1 vs v2

| 特性 | v1 `/api/skill/v1/execute` | v2 `/api/skill/v2/execute` |
|------|--------------------------|--------------------------|
| 基础执行 | 支持 | 支持 |
| `warnings` 字段 | 不含 | 包含 |
| `X-Skill-Version` 头 | 忽略 | 读取，检查兼容性 |
| 版本保证 | 永久保留，不做破坏性修改 | 当前最新，推荐使用 |

v1 长期保留，现有集成无需迁移。新接入建议使用 v2。

---

## 权限与套餐

### 套餐等级

| 套餐 | 可用技能 |
|------|---------|
| `free` | stock-query（搜索行情）、market-overview（日报，待实现） |
| `pro` | 以上全部 + tech-scan（技术面扫描）、fundamental-report（研报，待实现） |
| `admin` | 无限制，配额豁免 |

### 权限不足响应

```json
HTTP 403
{
  "detail": "Skill 'tech-scan:run' requires tier 'pro', user has 'free'"
}
```

升级套餐通过 `/api/subscription/upgrade` 完成（现有接口）。

---

## LLM 配额

调用会消耗 LLM 成本的技能（如 `tech-scan`）时，系统按月统计用量：

| 套餐 | 每月 LLM 调用上限 |
|------|----------------|
| `free` | 0（不可调用 LLM 技能） |
| `pro` | 100 次 |
| `admin` | 无限制 |

- 配额按自然月重置，每月 1 日 00:00 UTC 清零
- 超配返回 HTTP 429，响应包含重置时间：

```json
HTTP 429
{
  "error": "quota_exceeded",
  "detail": "LLM quota exceeded: 100/month for tier 'pro', resets 2026-05-01",
  "reset_at": "2026-05-01"
}
```

每次响应的 `meta` 字段均包含当前用量，便于客户端显示剩余配额。

---

## 已支持的技能清单

### stock-query / search

搜索股票行情数据，`free` 及以上可用，不消耗 LLM 配额。

**params：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `query` | string | `""` | 股票代码关键词，如 `"600519"` |
| `limit` | int | 10 | 返回条数，最大 50 |

**示例：**

```json
{
  "skill_id": "stock-query",
  "action": "search",
  "params": {"query": "600519", "limit": 3}
}
```

**data 响应：**

```json
{
  "stocks": [
    {"code": "600519.SH", "date": "2026-04-04", "open": 1520.0, "high": 1535.0,
     "low": 1515.0, "close": 1528.0, "vol": 12345.0}
  ]
}
```

---

### tech-scan / run

触发个股技术面扫描，`pro` 及以上可用，消耗 1 次 LLM 配额。

**params：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | 股票代码，如 `"601857"` 或 `"601857.SH"` |

**示例：**

```json
{
  "skill_id": "tech-scan",
  "action": "run",
  "params": {"code": "601857"}
}
```

**data 响应：**

```json
{
  "code": "601857",
  "status": "queued",
  "message": "Tech scan report will be generated. Check output/single_scan/ for results."
}
```

> 当前为异步排队模式，报告生成后存放于 `output/single_scan/`。

---

## 版本兼容

通过请求头 `X-Skill-Version` 声明客户端版本（仅 v2 端点生效）：

```
X-Skill-Version: 2
```

| 客户端版本 | 行为 |
|-----------|------|
| 等于当前版本（2） | 正常，`warnings: []` |
| 低于当前但 >= 最低（1） | 正常执行，`warnings` 包含"版本过旧"提示 |
| 低于最低支持版本（< 1） | 返回 HTTP 400，拒绝执行 |
| 超出范围（> 12） | 返回 HTTP 422 |

当前网关版本：**2**，最低支持版本：**1**。

---

## 错误代码速查

| HTTP 状态码 | 场景 | 说明 |
|------------|------|------|
| 400 | 短码无效/已过期 | `{"status": "invalid_code"}` |
| 400 | 客户端版本过旧 | 升级 Skill 版本 |
| 400 | 缺少必填参数 | 检查 `params` |
| 401 | 未携带 JWT 或已过期 | 重新走 Device Flow 获取新 token |
| 403 | 套餐不足 | 升级到对应套餐 |
| 404 | skill_id / action 未注册 | 检查技能名称拼写 |
| 429 | LLM 配额耗尽 | 等到下月重置，或升级套餐 |
| 429 | 轮询频率超限 | 降低轮询频率（建议 3-5 秒间隔） |

---

## 扩展：添加新技能

### 1. 添加 action handler

新建 `api/services/skill_actions/<skill_name>.py`：

```python
from sqlalchemy.ext.asyncio import AsyncSession

async def <action>(params: dict, db: AsyncSession) -> dict:
    # ... 业务逻辑
    return {"result": "..."}
```

如需 LLM 调用，参考 `tech_scan.py`，在函数开头调用 `LLMQuotaService.check_and_increment`。

### 2. 注册权限

在 `api/services/skill_permissions.py` 的 `SKILL_ACL` 中添加：

```python
SKILL_ACL["<skill_id>"] = {
    "<action>": UserTier.FREE.value,   # 或 UserTier.PRO.value
}
```

### 3. 注册 handler

在 `api/routers/skill_gateway.py` 的 `_ACTION_HANDLERS` 中添加：

```python
from api.services.skill_actions import <skill_module>

_ACTION_HANDLERS[("<skill_id>", "<action>")] = (
    lambda ctx: <skill_module>.<action>(ctx.params, ctx.db)
)
```

### 4. 补测试

参考 `tests/test_skill_gateway.py` 中已有用例，为新 handler 添加单元测试。

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `api/services/device_auth.py` | Device Flow Redis 短码逻辑 |
| `api/routers/skill_auth.py` | 认证端点（/device/code、/token、/verify） |
| `api/services/skill_permissions.py` | RBAC：SKILL_ACL、TIER_LLM_QUOTA |
| `api/services/llm_quota.py` | LLM 配额计数（Redis Lua 原子 INCR） |
| `api/routers/skill_gateway.py` | 执行端点 v1/v2，handler 注册表 |
| `api/services/skill_router.py` | 版本兼容检查（SkillRouter） |
| `api/services/skill_actions/` | 各技能 action 实现 |
| `tests/test_device_auth.py` | Device Flow 单元测试 |
| `tests/test_skill_gateway.py` | 网关集成测试 |
| `tests/test_skill_permissions.py` | RBAC 单元测试 |
| `tests/test_llm_quota.py` | 配额服务单元测试 |
| `tests/test_skill_versioning.py` | 版本兼容单元+集成测试 |
