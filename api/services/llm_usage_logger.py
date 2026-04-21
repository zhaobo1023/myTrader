"""
LLM usage logger (M2-T7): records per-skill LLM call metrics.

Writes to llm_usage_logs table asynchronously. All errors are swallowed
so a DB outage never disrupts the SSE stream.

Usage:
    logger = LLMUsageLogger(db_session_factory=get_db_session)
    rec = LLMCallRecord(skill_id='theme-review', model='qwen3.6-plus', latency_ms=0)
    async with logger.timed(rec):
        result = await llm_call(...)
    await logger.log(rec)
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger('myTrader.llm_usage')


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class LLMCallRecord:
    skill_id: str
    model: str
    latency_ms: int

    user_id: Optional[int] = None
    resource_id: Optional[int] = None   # e.g. theme_id
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ---------------------------------------------------------------------------
# ORM model (inline to avoid circular import from api.models)
# ---------------------------------------------------------------------------

class LLMUsageLog:
    """Lightweight non-declarative placeholder for the ORM row."""

    __tablename__ = 'llm_usage_logs'

    def __init__(
        self,
        skill_id: str,
        model: str,
        latency_ms: int,
        user_id: Optional[int],
        resource_id: Optional[int],
        prompt_tokens: int,
        completion_tokens: int,
        created_at: datetime,
    ):
        self.skill_id = skill_id
        self.model = model
        self.latency_ms = latency_ms
        self.user_id = user_id
        self.resource_id = resource_id
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.created_at = created_at


# ---------------------------------------------------------------------------
# Logger service
# ---------------------------------------------------------------------------

class LLMUsageLogger:
    """Async-safe fire-and-forget LLM usage recorder.

    Args:
        db_session_factory: Async callable that returns an async context manager
            yielding a SQLAlchemy AsyncSession. Pass None to disable logging.
    """

    def __init__(self, db_session_factory=None):
        self._db_factory = db_session_factory

    async def log(self, rec: LLMCallRecord) -> None:
        """Write a usage record to the DB. Never raises."""
        if self._db_factory is None:
            return
        try:
            orm_obj = LLMUsageLog(
                skill_id=rec.skill_id,
                model=rec.model,
                latency_ms=rec.latency_ms,
                user_id=rec.user_id,
                resource_id=rec.resource_id,
                prompt_tokens=rec.prompt_tokens,
                completion_tokens=rec.completion_tokens,
                created_at=datetime.now(),
            )
            session = await self._db_factory()
            async with session:
                session.add(orm_obj)
                await session.commit()
        except Exception as e:
            logger.warning('[LLMUsageLogger] failed to write usage log: %s', e)

    @asynccontextmanager
    async def timed(self, rec: LLMCallRecord):
        """Async context manager that sets rec.latency_ms on exit."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            rec.latency_ms = int((time.monotonic() - t0) * 1000)
