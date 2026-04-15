"""
LLM feedback service (M3-T3): records user ratings on LLM skill outputs.

A "helpful / unhelpful" signal for each skill invocation, stored in
llm_feedback table for future model fine-tuning or prompt improvement.

Usage:
    svc = LLMFeedbackService(db_session_factory=get_db_session)
    rec = FeedbackRecord(skill_id='theme-review', rating='helpful', user_id=42)
    await svc.submit(rec)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger('myTrader.llm_feedback')

VALID_RATINGS = {'helpful', 'unhelpful'}


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class FeedbackRecord:
    skill_id: str
    rating: str

    user_id: Optional[int] = None
    resource_id: Optional[int] = None   # e.g. theme_id, stock_code
    comment: Optional[str] = None

    def __post_init__(self):
        if self.rating not in VALID_RATINGS:
            raise ValueError(f"rating must be one of {VALID_RATINGS}, got {self.rating!r}")


# ---------------------------------------------------------------------------
# ORM placeholder
# ---------------------------------------------------------------------------

class LLMFeedback:
    """Lightweight non-declarative ORM row for llm_feedback table."""

    __tablename__ = 'llm_feedback'

    def __init__(
        self,
        skill_id: str,
        rating: str,
        user_id: Optional[int],
        resource_id: Optional[int],
        comment: Optional[str],
        created_at: datetime,
    ):
        self.skill_id = skill_id
        self.rating = rating
        self.user_id = user_id
        self.resource_id = resource_id
        self.comment = comment
        self.created_at = created_at


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LLMFeedbackService:
    """Async feedback recorder. All errors are swallowed."""

    def __init__(self, db_session_factory=None):
        self._db_factory = db_session_factory

    async def submit(self, rec: FeedbackRecord) -> None:
        """Write a feedback record to DB. Never raises."""
        if self._db_factory is None:
            return
        try:
            orm_obj = LLMFeedback(
                skill_id=rec.skill_id,
                rating=rec.rating,
                user_id=rec.user_id,
                resource_id=rec.resource_id,
                comment=rec.comment,
                created_at=datetime.utcnow(),
            )
            session = await self._db_factory()
            async with session:
                session.add(orm_obj)
                await session.commit()
        except Exception as e:
            logger.warning('[LLMFeedbackService] failed to save feedback: %s', e)

    async def get_stats(self, skill_id: str) -> dict[str, int]:
        """Return helpful/unhelpful counts for a skill. Returns {rating: count}."""
        if self._db_factory is None:
            return {r: 0 for r in VALID_RATINGS}
        try:
            session = await self._db_factory()
            async with session:
                result = await session.execute(
                    "SELECT rating, COUNT(*) as count FROM llm_feedback "
                    "WHERE skill_id = :skill_id GROUP BY rating",
                    {'skill_id': skill_id},
                )
                rows = result.fetchall()
                counts = {r: 0 for r in VALID_RATINGS}
                for row in rows:
                    if row.rating in counts:
                        counts[row.rating] = row.count
                return counts
        except Exception as e:
            logger.warning('[LLMFeedbackService] get_stats failed: %s', e)
            return {r: 0 for r in VALID_RATINGS}
