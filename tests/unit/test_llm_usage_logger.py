"""
Unit tests for api/services/llm_usage_logger.py (M2-T7)
- LLMUsageLogger: records skill invocation latency and token counts
- async-safe, fire-and-forget, never raises
"""
import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.llm_usage_logger import LLMUsageLogger, LLMCallRecord


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# TestLLMCallRecord
# ---------------------------------------------------------------------------

class TestLLMCallRecord(unittest.TestCase):

    def test_required_fields(self):
        rec = LLMCallRecord(skill_id='theme-review', model='qwen3.6-plus', latency_ms=1500)
        self.assertEqual(rec.skill_id, 'theme-review')
        self.assertEqual(rec.model, 'qwen3.6-plus')
        self.assertEqual(rec.latency_ms, 1500)

    def test_optional_fields_default_to_none_or_zero(self):
        rec = LLMCallRecord(skill_id='theme-create', model='qwen3.6-plus', latency_ms=800)
        self.assertIsNone(rec.user_id)
        self.assertIsNone(rec.resource_id)
        self.assertEqual(rec.prompt_tokens, 0)
        self.assertEqual(rec.completion_tokens, 0)

    def test_total_tokens_property(self):
        rec = LLMCallRecord(
            skill_id='theme-review', model='qwen3.6-plus', latency_ms=1000,
            prompt_tokens=500, completion_tokens=200,
        )
        self.assertEqual(rec.total_tokens, 700)


# ---------------------------------------------------------------------------
# TestLLMUsageLogger
# ---------------------------------------------------------------------------

class TestLLMUsageLogger(unittest.TestCase):

    def _make_logger(self):
        mock_db_factory = AsyncMock()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_db_factory.return_value = mock_session
        logger = LLMUsageLogger(db_session_factory=mock_db_factory)
        return logger, mock_session

    def test_log_writes_to_db(self):
        """log() should add a record and commit."""
        logger, session = self._make_logger()
        rec = LLMCallRecord(skill_id='theme-review', model='qwen3.6-plus', latency_ms=1200)
        _run(logger.log(rec))
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    def test_log_does_not_raise_on_db_error(self):
        """If DB write fails, log() must swallow the exception."""
        mock_db_factory = AsyncMock()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception('db error'))
        mock_db_factory.return_value = mock_session
        logger = LLMUsageLogger(db_session_factory=mock_db_factory)

        rec = LLMCallRecord(skill_id='theme-review', model='qwen3.6-plus', latency_ms=500)
        # must not raise
        _run(logger.log(rec))

    def test_log_record_fields_saved(self):
        """The ORM object added to session should carry all record fields."""
        logger, session = self._make_logger()
        rec = LLMCallRecord(
            skill_id='theme-create',
            model='deepseek-chat',
            latency_ms=2500,
            user_id=42,
            resource_id=7,
            prompt_tokens=300,
            completion_tokens=150,
        )
        _run(logger.log(rec))

        orm_obj = session.add.call_args[0][0]
        self.assertEqual(orm_obj.skill_id, 'theme-create')
        self.assertEqual(orm_obj.model, 'deepseek-chat')
        self.assertEqual(orm_obj.latency_ms, 2500)
        self.assertEqual(orm_obj.user_id, 42)
        self.assertEqual(orm_obj.resource_id, 7)
        self.assertEqual(orm_obj.prompt_tokens, 300)
        self.assertEqual(orm_obj.completion_tokens, 150)

    def test_timed_context_measures_latency(self):
        """timed() context manager should capture elapsed time."""
        logger, session = self._make_logger()
        base_rec = LLMCallRecord(skill_id='theme-review', model='qwen3.6-plus', latency_ms=0)

        async def _use_timed():
            async with logger.timed(base_rec):
                await asyncio.sleep(0.05)  # 50ms
            await logger.log(base_rec)

        _run(_use_timed())
        # latency_ms should be at least 50
        self.assertGreaterEqual(base_rec.latency_ms, 40)

    def test_log_without_db_factory_is_noop(self):
        """LLMUsageLogger(db_session_factory=None) should be a safe no-op."""
        logger = LLMUsageLogger(db_session_factory=None)
        rec = LLMCallRecord(skill_id='theme-review', model='qwen3.6-plus', latency_ms=100)
        # must not raise
        _run(logger.log(rec))


if __name__ == '__main__':
    unittest.main()
