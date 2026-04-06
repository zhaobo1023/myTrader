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

    async def poll_code(self, code: str):
        """
        Atomically check and conditionally delete a device code.

        Returns:
            "missing" - code does not exist (expired or invalid)
            None      - code exists but not yet verified (pending)
            int       - user_id after verification (key is deleted atomically)
        """
        key = f"{CODE_PREFIX}{code}"
        # Lua script: get the key; if not found return {0, ""}.
        # If found but user_id is null/false (pending), return {0, raw_json}.
        # If found and user_id is a number, delete the key and return {1, user_id_string}.
        lua = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return {0, ''}
end
local ok, data = pcall(cjson.decode, raw)
if not ok then
    return {0, ''}
end
local uid = data['user_id']
if uid == cjson.null or uid == false or uid == nil then
    return {0, raw}
end
redis.call('DEL', KEYS[1])
return {1, tostring(uid)}
"""
        result = await self.redis.eval(lua, 1, key)
        found, value = result[0], result[1]
        if not found:
            if not value:
                return "missing"  # key did not exist
            return None  # key exists but pending
        return int(value)  # verified, key deleted atomically

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
