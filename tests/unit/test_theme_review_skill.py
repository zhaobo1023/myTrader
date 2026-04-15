"""
Unit tests for api/services/llm_skills/theme_review.py (M2-T4)
- ThemeReviewSkill: reads theme stocks, calls LLM to evaluate each stock's thesis
- SSE event sequence: start -> loading_stocks -> reviewing -> review_result -> done / error
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.llm_skills.theme_review import ThemeReviewSkill, VERDICTS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _collect(skill, **kwargs) -> list[dict]:
    events = []

    async def _gather():
        async for ev in skill.stream(**kwargs):
            events.append(ev)

    _run(_gather())
    return events


def _make_stocks(n: int = 3) -> list[dict]:
    return [
        {
            'stock_code': f'{str(i).zfill(6)}.SZ',
            'stock_name': f'测试股票{i}',
            'total_score': float(50 + i),
            'reason': f'入池理由{i}',
        }
        for i in range(1, n + 1)
    ]


def _make_llm_response(stocks: list[dict], verdict: str = 'hold') -> str:
    """Build a well-formed LLM response for the given stocks."""
    return json.dumps({
        'reviews': [
            {
                'stock_code': s['stock_code'],
                'verdict': verdict,
                'reason': f'评估理由-{s["stock_name"]}',
            }
            for s in stocks
        ]
    })


def _make_skill(stocks: list[dict], llm_response: str) -> ThemeReviewSkill:
    """Create ThemeReviewSkill with mocked stock loader and LLM."""
    skill = ThemeReviewSkill.__new__(ThemeReviewSkill)
    skill._load_stocks = AsyncMock(return_value=stocks)
    mock_factory = MagicMock()
    mock_factory.call = AsyncMock(return_value=llm_response)
    skill._llm_factory = mock_factory
    return skill


# ---------------------------------------------------------------------------
# TestVerdicts
# ---------------------------------------------------------------------------

class TestVerdicts(unittest.TestCase):
    def test_verdicts_contains_hold(self):
        self.assertIn('hold', VERDICTS)

    def test_verdicts_contains_watch(self):
        self.assertIn('watch', VERDICTS)

    def test_verdicts_contains_exit(self):
        self.assertIn('exit', VERDICTS)

    def test_each_verdict_has_label(self):
        for v, label in VERDICTS.items():
            self.assertIsInstance(label, str)
            self.assertTrue(len(label) > 0)


# ---------------------------------------------------------------------------
# TestThemeReviewSkillMeta
# ---------------------------------------------------------------------------

class TestThemeReviewSkillMeta(unittest.TestCase):
    def test_skill_id(self):
        skill = ThemeReviewSkill()
        self.assertEqual(skill.meta.skill_id, 'theme-review')

    def test_meta_has_name(self):
        skill = ThemeReviewSkill()
        self.assertTrue(len(skill.meta.name) > 0)


# ---------------------------------------------------------------------------
# TestThemeReviewStream
# ---------------------------------------------------------------------------

class TestThemeReviewStream(unittest.TestCase):

    def test_stream_starts_with_start_event(self):
        stocks = _make_stocks(2)
        skill = _make_skill(stocks, _make_llm_response(stocks))
        events = _collect(skill, theme_id=1)
        self.assertEqual(events[0]['type'], 'start')

    def test_stream_ends_with_done_event(self):
        stocks = _make_stocks(2)
        skill = _make_skill(stocks, _make_llm_response(stocks))
        events = _collect(skill, theme_id=1)
        self.assertEqual(events[-1]['type'], 'done')
        self.assertNotIn('error', [e['type'] for e in events])

    def test_stream_has_loading_stocks_event(self):
        stocks = _make_stocks(3)
        skill = _make_skill(stocks, _make_llm_response(stocks))
        events = _collect(skill, theme_id=1)
        types = [e['type'] for e in events]
        self.assertIn('loading_stocks', types)

    def test_stream_has_review_result_event(self):
        stocks = _make_stocks(2)
        skill = _make_skill(stocks, _make_llm_response(stocks))
        events = _collect(skill, theme_id=1)
        result_events = [e for e in events if e['type'] == 'review_result']
        self.assertEqual(len(result_events), 1)

    def test_review_result_contains_all_stocks(self):
        stocks = _make_stocks(3)
        skill = _make_skill(stocks, _make_llm_response(stocks))
        events = _collect(skill, theme_id=1)
        result = next(e for e in events if e['type'] == 'review_result')
        self.assertEqual(len(result['reviews']), 3)

    def test_review_result_each_item_has_required_fields(self):
        stocks = _make_stocks(2)
        skill = _make_skill(stocks, _make_llm_response(stocks))
        events = _collect(skill, theme_id=1)
        result = next(e for e in events if e['type'] == 'review_result')
        for item in result['reviews']:
            self.assertIn('stock_code', item)
            self.assertIn('verdict', item)
            self.assertIn('reason', item)

    def test_review_result_verdict_is_valid(self):
        stocks = _make_stocks(2)
        skill = _make_skill(stocks, _make_llm_response(stocks, verdict='watch'))
        events = _collect(skill, theme_id=1)
        result = next(e for e in events if e['type'] == 'review_result')
        for item in result['reviews']:
            self.assertIn(item['verdict'], VERDICTS)

    def test_llm_parse_error_returns_fallback_hold(self):
        """If LLM returns bad JSON, all stocks get 'hold' as fallback."""
        stocks = _make_stocks(2)
        skill = _make_skill(stocks, 'not valid json at all')
        events = _collect(skill, theme_id=1)
        result_events = [e for e in events if e['type'] == 'review_result']
        self.assertEqual(len(result_events), 1)
        for item in result_events[0]['reviews']:
            self.assertEqual(item['verdict'], 'hold')

    def test_empty_theme_returns_done_with_zero_reviews(self):
        """A theme with no stocks should still complete gracefully."""
        skill = _make_skill([], '{"reviews": []}')
        events = _collect(skill, theme_id=1)
        types = [e['type'] for e in events]
        self.assertIn('done', types)
        self.assertNotIn('error', types)

    def test_error_event_on_unexpected_exception(self):
        """If load_stocks raises, stream must yield error event, not propagate."""
        skill = ThemeReviewSkill.__new__(ThemeReviewSkill)
        skill._load_stocks = AsyncMock(side_effect=RuntimeError('db down'))
        mock_factory = MagicMock()
        mock_factory.call = AsyncMock(return_value='{}')
        skill._llm_factory = mock_factory

        events = _collect(skill, theme_id=1)
        types = [e['type'] for e in events]
        self.assertIn('error', types)

    def test_done_event_has_summary(self):
        stocks = _make_stocks(3)
        skill = _make_skill(stocks, _make_llm_response(stocks))
        events = _collect(skill, theme_id=1)
        done = next(e for e in events if e['type'] == 'done')
        self.assertIn('summary', done)

    def test_done_summary_counts_verdicts(self):
        stocks = _make_stocks(2)
        resp = json.dumps({'reviews': [
            {'stock_code': stocks[0]['stock_code'], 'verdict': 'hold', 'reason': 'ok'},
            {'stock_code': stocks[1]['stock_code'], 'verdict': 'exit', 'reason': 'weak'},
        ]})
        skill = _make_skill(stocks, resp)
        events = _collect(skill, theme_id=1)
        done = next(e for e in events if e['type'] == 'done')
        # summary should mention the counts of different verdicts
        self.assertIn('hold_count', done)
        self.assertIn('exit_count', done)


if __name__ == '__main__':
    unittest.main()
