import json
import secrets
import string
from datetime import datetime, timezone
import redis.asyncio as aioredis

CODE_TTL = 5 * 60  # 5 minutes
CODE_PREFIX = "skill:device:"


class DeviceAuthService:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _make_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(6))

    async def create_code(self) -> dict:
        code = self._make_code()
        payload = json.dumps({"user_id": None, "created_at": datetime.now(timezone.utc).isoformat()})
        await self.redis.setex(f"{CODE_PREFIX}{code}", CODE_TTL, payload)
        return {"code": code, "expires_in": CODE_TTL}

    async def poll_code(self, code: str) -> int | None:
        raw = await self.redis.get(f"{CODE_PREFIX}{code}")
        if raw is None:
            return None
        data = json.loads(raw)
        return data.get("user_id")

    async def verify_code(self, code: str, user_id: int) -> bool:
        key = f"{CODE_PREFIX}{code}"
        lua = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, data = pcall(cjson.decode, raw)
if not ok then return 0 end
if data['user_id'] ~= cjson.null and data['user_id'] ~= false then return 0 end
data['user_id'] = tonumber(ARGV[1])
local ttl = redis.call('TTL', KEYS[1])
if ttl <= 0 then ttl = 1 end
redis.call('SETEX', KEYS[1], ttl, cjson.encode(data))
return 1
"""
        result = await self.redis.eval(lua, 1, key, str(user_id))
        return bool(result)
