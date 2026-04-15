"""
Unit tests for api/services/llm_skills/portfolio_doctor.py (M3-T1)

PortfolioDoctorSkill:
  - Reads holdings (stock_code, stock_name, industry, weight, cost, current_price, pnl_pct)
  - Computes concentration metrics (top-3 weight, industry distribution, theme overlap)
  - One LLM call -> free-text + structured suggestions
  - SSE: start -> loading -> analyzing -> diagnosis -> done / error
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.llm_skills.portfolio_doctor import (
    PortfolioDoctorSkill,
    compute_concentration,
    HoldingItem,
)


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


def _make_holdings(n: int = 4) -> list[HoldingItem]:
    industries = ['电力设备', '电力设备', '半导体', '消费']
    return [
        HoldingItem(
            stock_code=f'{str(i).zfill(6)}.SZ',
            stock_name=f'股票{i}',
            industry=industries[i % len(industries)],
            weight=25.0,
            cost=10.0 * i,
            current_price=10.0 * i * (1 + 0.05 * i),
            pnl_pct=5.0 * i,
        )
        for i in range(1, n + 1)
    ]


def _make_llm_response(summary: str = '持仓结构合理') -> str:
    return json.dumps({
        'summary': summary,
        'risks': ['行业集中度偏高', '单票权重过大'],
        'suggestions': [
            {'action': '减持', 'stock_code': '000001.SZ', 'reason': '权重已超20%'},
            {'action': '分散', 'stock_code': None, 'reason': '建议增加消费板块配置'},
        ],
    })


def _make_skill(holdings: list[HoldingItem], llm_response: str) -> PortfolioDoctorSkill:
    skill = PortfolioDoctorSkill.__new__(PortfolioDoctorSkill)
    skill._load_holdings = AsyncMock(return_value=holdings)
    mock_factory = MagicMock()
    mock_factory.call = AsyncMock(return_value=llm_response)
    skill._llm_factory = mock_factory
    return skill


# ---------------------------------------------------------------------------
# TestComputeConcentration
# ---------------------------------------------------------------------------

class TestComputeConcentration(unittest.TestCase):

    def test_top3_weight(self):
        holdings = _make_holdings(5)
        metrics = compute_concentration(holdings)
        # Each holding weight=25, top3=75
        self.assertIn('top3_weight', metrics)
        self.assertAlmostEqual(metrics['top3_weight'], 75.0, places=1)

    def test_industry_distribution(self):
        holdings = _make_holdings(4)
        metrics = compute_concentration(holdings)
        self.assertIn('industry_distribution', metrics)
        dist = metrics['industry_distribution']
        # 2 of 4 stocks are 电力设备 (indices 0,1 mod 4), so it has 50%
        self.assertIn('电力设备', dist)
        self.assertAlmostEqual(dist['电力设备'], 50.0, places=0)

    def test_max_single_weight(self):
        holdings = _make_holdings(3)
        metrics = compute_concentration(holdings)
        self.assertIn('max_single_weight', metrics)
        self.assertAlmostEqual(metrics['max_single_weight'], 25.0, places=1)

    def test_stock_count(self):
        holdings = _make_holdings(6)
        metrics = compute_concentration(holdings)
        self.assertEqual(metrics['stock_count'], 6)

    def test_empty_holdings(self):
        metrics = compute_concentration([])
        self.assertEqual(metrics['stock_count'], 0)
        self.assertEqual(metrics['top3_weight'], 0.0)


# ---------------------------------------------------------------------------
# TestPortfolioDoctorSkillMeta
# ---------------------------------------------------------------------------

class TestPortfolioDoctorSkillMeta(unittest.TestCase):

    def test_skill_id(self):
        skill = PortfolioDoctorSkill()
        self.assertEqual(skill.meta.skill_id, 'portfolio-doctor')

    def test_meta_name_not_empty(self):
        self.assertTrue(len(PortfolioDoctorSkill().meta.name) > 0)


# ---------------------------------------------------------------------------
# TestPortfolioDoctorStream
# ---------------------------------------------------------------------------

class TestPortfolioDoctorStream(unittest.TestCase):

    def test_stream_starts_with_start(self):
        skill = _make_skill(_make_holdings(), _make_llm_response())
        events = _collect(skill, user_id=1)
        self.assertEqual(events[0]['type'], 'start')

    def test_stream_ends_with_done(self):
        skill = _make_skill(_make_holdings(), _make_llm_response())
        events = _collect(skill, user_id=1)
        self.assertEqual(events[-1]['type'], 'done')
        self.assertNotIn('error', [e['type'] for e in events])

    def test_stream_has_diagnosis_event(self):
        skill = _make_skill(_make_holdings(), _make_llm_response())
        events = _collect(skill, user_id=1)
        types = [e['type'] for e in events]
        self.assertIn('diagnosis', types)

    def test_diagnosis_has_summary(self):
        skill = _make_skill(_make_holdings(), _make_llm_response('组合均衡'))
        events = _collect(skill, user_id=1)
        diag = next(e for e in events if e['type'] == 'diagnosis')
        self.assertIn('summary', diag)
        self.assertEqual(diag['summary'], '组合均衡')

    def test_diagnosis_has_risks(self):
        skill = _make_skill(_make_holdings(), _make_llm_response())
        events = _collect(skill, user_id=1)
        diag = next(e for e in events if e['type'] == 'diagnosis')
        self.assertIn('risks', diag)
        self.assertIsInstance(diag['risks'], list)

    def test_diagnosis_has_suggestions(self):
        skill = _make_skill(_make_holdings(), _make_llm_response())
        events = _collect(skill, user_id=1)
        diag = next(e for e in events if e['type'] == 'diagnosis')
        self.assertIn('suggestions', diag)
        self.assertIsInstance(diag['suggestions'], list)

    def test_diagnosis_has_concentration_metrics(self):
        skill = _make_skill(_make_holdings(), _make_llm_response())
        events = _collect(skill, user_id=1)
        diag = next(e for e in events if e['type'] == 'diagnosis')
        self.assertIn('concentration', diag)
        c = diag['concentration']
        self.assertIn('top3_weight', c)
        self.assertIn('industry_distribution', c)

    def test_empty_holdings_returns_done(self):
        skill = _make_skill([], '{"summary": "空仓", "risks": [], "suggestions": []}')
        events = _collect(skill, user_id=1)
        types = [e['type'] for e in events]
        self.assertIn('done', types)
        self.assertNotIn('error', types)

    def test_llm_parse_error_returns_fallback(self):
        skill = _make_skill(_make_holdings(), 'not valid json')
        events = _collect(skill, user_id=1)
        diag_events = [e for e in events if e['type'] == 'diagnosis']
        self.assertEqual(len(diag_events), 1)
        self.assertIn('summary', diag_events[0])

    def test_error_event_on_load_failure(self):
        skill = PortfolioDoctorSkill.__new__(PortfolioDoctorSkill)
        skill._load_holdings = AsyncMock(side_effect=RuntimeError('db down'))
        mock_factory = MagicMock()
        mock_factory.call = AsyncMock(return_value='{}')
        skill._llm_factory = mock_factory
        events = _collect(skill, user_id=1)
        self.assertIn('error', [e['type'] for e in events])


if __name__ == '__main__':
    unittest.main()
