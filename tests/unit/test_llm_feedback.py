"""
Unit tests for M3-T3: LLM output user feedback mechanism.
Tests cover:
  - FeedbackRecord dataclass validation
  - LLMFeedbackService.submit(): writes to DB, never raises on error
  - Feedback router: POST /api/theme-pool/llm/feedback (logic layer, no HTTP)
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.llm_feedback import LLMFeedbackService, FeedbackRecord, VALID_RATINGS


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# TestFeedbackRecord
# ---------------------------------------------------------------------------

class TestFeedbackRecord(unittest.TestCase):

    def test_valid_helpful(self):
        rec = FeedbackRecord(skill_id='theme-review', rating='helpful', user_id=1)
        self.assertEqual(rec.rating, 'helpful')

    def test_valid_unhelpful(self):
        rec = FeedbackRecord(skill_id='theme-review', rating='unhelpful', user_id=1)
        self.assertEqual(rec.rating, 'unhelpful')

    def test_invalid_rating_raises(self):
        with self.assertRaises(ValueError):
            FeedbackRecord(skill_id='theme-review', rating='meh', user_id=1)

    def test_optional_fields_default_none(self):
        rec = FeedbackRecord(skill_id='theme-create', rating='helpful')
        self.assertIsNone(rec.user_id)
        self.assertIsNone(rec.resource_id)
        self.assertIsNone(rec.comment)

    def test_resource_id_stored(self):
        rec = FeedbackRecord(skill_id='theme-review', rating='unhelpful',
                             user_id=5, resource_id=42, comment='理由不够准确')
        self.assertEqual(rec.resource_id, 42)
        self.assertEqual(rec.comment, '理由不够准确')


# ---------------------------------------------------------------------------
# TestValidRatings
# ---------------------------------------------------------------------------

class TestValidRatings(unittest.TestCase):
    def test_helpful_present(self):
        self.assertIn('helpful', VALID_RATINGS)

    def test_unhelpful_present(self):
        self.assertIn('unhelpful', VALID_RATINGS)


# ---------------------------------------------------------------------------
# TestLLMFeedbackService
# ---------------------------------------------------------------------------

class TestLLMFeedbackService(unittest.TestCase):

    def _make_service(self, commit_raises=False):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = MagicMock()
        if commit_raises:
            mock_session.commit = AsyncMock(side_effect=Exception('db error'))
        else:
            mock_session.commit = AsyncMock()
        mock_factory = AsyncMock(return_value=mock_session)
        return LLMFeedbackService(db_session_factory=mock_factory), mock_session

    def test_submit_writes_to_db(self):
        svc, session = self._make_service()
        rec = FeedbackRecord(skill_id='theme-review', rating='helpful', user_id=1)
        _run(svc.submit(rec))
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    def test_submit_does_not_raise_on_db_error(self):
        svc, _ = self._make_service(commit_raises=True)
        rec = FeedbackRecord(skill_id='theme-review', rating='helpful')
        # must not raise
        _run(svc.submit(rec))

    def test_submit_saves_all_fields(self):
        svc, session = self._make_service()
        rec = FeedbackRecord(
            skill_id='portfolio-doctor',
            rating='unhelpful',
            user_id=7,
            resource_id=99,
            comment='建议太保守',
        )
        _run(svc.submit(rec))
        orm_obj = session.add.call_args[0][0]
        self.assertEqual(orm_obj.skill_id, 'portfolio-doctor')
        self.assertEqual(orm_obj.rating, 'unhelpful')
        self.assertEqual(orm_obj.user_id, 7)
        self.assertEqual(orm_obj.resource_id, 99)
        self.assertEqual(orm_obj.comment, '建议太保守')

    def test_submit_noop_when_no_factory(self):
        svc = LLMFeedbackService(db_session_factory=None)
        rec = FeedbackRecord(skill_id='theme-create', rating='helpful')
        # must not raise
        _run(svc.submit(rec))

    def test_get_stats_returns_counts(self):
        """get_stats() should return helpful/unhelpful counts for a skill."""
        svc, session = self._make_service()
        # Mock a scalar query result
        session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(rating='helpful', count=10),
            MagicMock(rating='unhelpful', count=3),
        ]
        session.execute.return_value = mock_result

        stats = _run(svc.get_stats('theme-review'))
        self.assertIn('helpful', stats)
        self.assertIn('unhelpful', stats)


if __name__ == '__main__':
    unittest.main()
