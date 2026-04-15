"""
Unit tests for the unified /api/theme-pool/llm/stream endpoint (M2-T6).
Tests the registry routing logic directly without starting FastAPI.
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.llm_skills.registry import get_skill, list_skills, _REGISTRY


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# TestRegistry
# ---------------------------------------------------------------------------

class TestRegistry(unittest.TestCase):

    def test_theme_review_registered(self):
        """ThemeReviewSkill must auto-register when module is imported."""
        import api.services.llm_skills.theme_review  # trigger registration
        skill = get_skill('theme-review')
        self.assertIsNotNone(skill)

    def test_get_skill_unknown_returns_none(self):
        skill = get_skill('nonexistent-skill-xyz')
        self.assertIsNone(skill)

    def test_list_skills_returns_list(self):
        import api.services.llm_skills.theme_review
        skills = list_skills()
        self.assertIsInstance(skills, list)

    def test_list_skills_includes_theme_review(self):
        import api.services.llm_skills.theme_review
        skills = list_skills()
        ids = [s['skill_id'] for s in skills]
        self.assertIn('theme-review', ids)

    def test_list_skills_each_item_has_required_keys(self):
        import api.services.llm_skills.theme_review
        for s in list_skills():
            self.assertIn('skill_id', s)
            self.assertIn('name', s)
            self.assertIn('version', s)
            self.assertIn('description', s)


# ---------------------------------------------------------------------------
# TestLLMStreamDispatch (logic layer, no HTTP)
# ---------------------------------------------------------------------------

class TestLLMStreamDispatch(unittest.TestCase):
    """Test the dispatch logic used by the /llm/stream endpoint."""

    def _dispatch(self, skill_id: str, params: dict) -> list[dict]:
        """Simulate what the router does: get skill, call stream, collect events."""
        import api.services.llm_skills.theme_review

        skill = get_skill(skill_id)
        if skill is None:
            return [{'type': 'error', 'message': f'Unknown skill: {skill_id}'}]

        events = []

        async def _gather():
            async for ev in skill.stream(**params):
                events.append(ev)

        _run(_gather())
        return events

    def test_unknown_skill_returns_error(self):
        events = self._dispatch('nonexistent', {})
        self.assertEqual(events[0]['type'], 'error')
        self.assertIn('nonexistent', events[0]['message'])

    def test_theme_review_dispatch_with_mocked_internals(self):
        import api.services.llm_skills.theme_review
        from api.services.llm_skills.theme_review import ThemeReviewSkill

        skill = get_skill('theme-review')
        # Mock internals so no real DB/LLM calls
        stocks = [{'stock_code': '000001.SZ', 'stock_name': '平安银行', 'reason': '测试', 'total_score': 60.0}]
        skill._load_stocks = AsyncMock(return_value=stocks)
        mock_factory = MagicMock()
        mock_factory.call = AsyncMock(return_value=json.dumps({
            'reviews': [{'stock_code': '000001.SZ', 'verdict': 'hold', 'reason': '逻辑完整'}]
        }))
        skill._llm_factory = mock_factory

        events = []

        async def _gather():
            async for ev in skill.stream(theme_id=42, theme_name='电网设备'):
                events.append(ev)

        _run(_gather())
        types = [e['type'] for e in events]
        self.assertIn('done', types)
        self.assertNotIn('error', types)
        result_ev = next(e for e in events if e['type'] == 'review_result')
        self.assertEqual(result_ev['reviews'][0]['verdict'], 'hold')


if __name__ == '__main__':
    unittest.main()
