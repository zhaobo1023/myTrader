"""
Unit tests for api/services/llm_skills/signal_interpreter.py (M3-T2)

SignalInterpreterSkill:
  - Input: stock_code, plus optional context (theme memberships, scores)
  - Fetches tech signals from DB (MA position, MACD, RSI, volume)
  - One LLM call -> structured natural-language investment summary
  - SSE: start -> loading_signals -> interpreting -> interpretation -> done / error
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.llm_skills.signal_interpreter import SignalInterpreterSkill


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


def _make_signals() -> dict:
    return {
        'stock_code': '000001.SZ',
        'stock_name': '平安银行',
        'close': 12.5,
        'ma5': 12.1, 'ma20': 11.8, 'ma60': 11.2,
        'macd': 0.15, 'macd_signal': 0.10, 'macd_hist': 0.05,
        'rsi14': 58.0,
        'volume_ratio': 1.3,
        'return_5d': 2.1,
        'return_20d': 5.8,
        'rps_20': 72,
        'total_score': 68.0,
    }


def _make_llm_response() -> str:
    return json.dumps({
        'stance': 'bullish',
        'summary': '股价站上多条均线，MACD 金叉，短期动能强劲。',
        'key_signals': ['均线多头排列', 'MACD 金叉', 'RSI 健康区间'],
        'risk_factors': ['量能未明显放大，需确认'],
        'suggested_action': '可在回踩 MA5 时轻仓介入',
    })


def _make_skill(signals: dict, llm_response: str) -> SignalInterpreterSkill:
    skill = SignalInterpreterSkill.__new__(SignalInterpreterSkill)
    skill._load_signals = AsyncMock(return_value=signals)
    mock_factory = MagicMock()
    mock_factory.call = AsyncMock(return_value=llm_response)
    skill._llm_factory = mock_factory
    return skill


# ---------------------------------------------------------------------------
# TestSignalInterpreterSkillMeta
# ---------------------------------------------------------------------------

class TestSignalInterpreterSkillMeta(unittest.TestCase):

    def test_skill_id(self):
        self.assertEqual(SignalInterpreterSkill().meta.skill_id, 'signal-interpreter')

    def test_meta_name_not_empty(self):
        self.assertTrue(len(SignalInterpreterSkill().meta.name) > 0)


# ---------------------------------------------------------------------------
# TestSignalInterpreterStream
# ---------------------------------------------------------------------------

class TestSignalInterpreterStream(unittest.TestCase):

    def test_stream_starts_with_start(self):
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        self.assertEqual(events[0]['type'], 'start')

    def test_stream_ends_with_done(self):
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        self.assertEqual(events[-1]['type'], 'done')
        self.assertNotIn('error', [e['type'] for e in events])

    def test_stream_has_interpretation_event(self):
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        types = [e['type'] for e in events]
        self.assertIn('interpretation', types)

    def test_interpretation_has_stance(self):
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        interp = next(e for e in events if e['type'] == 'interpretation')
        self.assertIn('stance', interp)
        self.assertIn(interp['stance'], ['bullish', 'bearish', 'neutral'])

    def test_interpretation_has_summary(self):
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        interp = next(e for e in events if e['type'] == 'interpretation')
        self.assertIn('summary', interp)
        self.assertTrue(len(interp['summary']) > 0)

    def test_interpretation_has_key_signals(self):
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        interp = next(e for e in events if e['type'] == 'interpretation')
        self.assertIn('key_signals', interp)
        self.assertIsInstance(interp['key_signals'], list)

    def test_interpretation_has_suggested_action(self):
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        interp = next(e for e in events if e['type'] == 'interpretation')
        self.assertIn('suggested_action', interp)

    def test_llm_parse_error_returns_fallback(self):
        """Bad JSON -> fallback interpretation with raw text as summary."""
        skill = _make_skill(_make_signals(), 'not valid json here at all')
        events = _collect(skill, stock_code='000001.SZ')
        interp_events = [e for e in events if e['type'] == 'interpretation']
        self.assertEqual(len(interp_events), 1)
        self.assertIn('summary', interp_events[0])

    def test_signals_not_found_returns_error(self):
        """If load_signals returns None, stream should emit error event."""
        skill = _make_skill(None, '{}')
        events = _collect(skill, stock_code='999999.SZ')
        types = [e['type'] for e in events]
        self.assertIn('error', types)

    def test_load_signals_db_error_returns_error(self):
        skill = SignalInterpreterSkill.__new__(SignalInterpreterSkill)
        skill._load_signals = AsyncMock(side_effect=RuntimeError('db down'))
        mock_factory = MagicMock()
        mock_factory.call = AsyncMock(return_value='{}')
        skill._llm_factory = mock_factory
        events = _collect(skill, stock_code='000001.SZ')
        self.assertIn('error', [e['type'] for e in events])

    def test_interpretation_includes_raw_signals(self):
        """interpretation event should echo back the key signal values."""
        skill = _make_skill(_make_signals(), _make_llm_response())
        events = _collect(skill, stock_code='000001.SZ')
        interp = next(e for e in events if e['type'] == 'interpretation')
        self.assertIn('signals_snapshot', interp)


if __name__ == '__main__':
    unittest.main()
