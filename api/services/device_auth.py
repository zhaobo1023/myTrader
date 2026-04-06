import json
import random
import string
from datetime import datetime
import redis.asyncio as aioredis

CODE_TTL = 300
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
        raw = await self.redis.get(f"{CODE_PREFIX}{code}")
        if raw is None:
            return None
        data = json.loads(raw)
        return data.get("user_id")

    async def verify_code(self, code: str, user_id: int) -> bool:
        key = f"{CODE_PREFIX}{code}"
        raw = await self.redis.get(key)
        if raw is None:
            return False
        data = json.loads(raw)
        if data["user_id"] is not None:
            return False
        data["user_id"] = user_id
        ttl = await self.redis.ttl(key)
        await self.redis.setex(key, max(ttl, 1), json.dumps(data))
        return True
