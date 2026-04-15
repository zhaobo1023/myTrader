# -*- coding: utf-8 -*-
"""
Unit tests for api/services/theme_llm_service.py

Test strategy:
  - Step 1: StockCodeValidator._normalize  (pure function, no I/O)
  - Step 2: StockCodeValidator.validate_batch  (mock DB)
  - Step 3: AKShareConceptFetcher (mock akshare)
  - Step 4: ThemeCreateSkill._extract_json / _fuzzy_match_boards (pure)
  - Step 5: ThemeCreateSkill._map_concepts / _filter_stocks / _supplement_stocks (mock LLM)
  - Step 6: ThemeCreateSkill.stream full flow (mock LLM + AKShare + DB)
"""
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from api.services.theme_llm_service import (
    StockCodeValidator,
    AKShareConceptFetcher,
    ThemeCreateSkill,
)


# ---------------------------------------------------------------------------
# Step 1: StockCodeValidator._normalize  (pure function)
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_sz_prefix_0(self):
        assert StockCodeValidator._normalize('000001') == '000001.SZ'

    def test_sz_prefix_3(self):
        assert StockCodeValidator._normalize('300750') == '300750.SZ'

    def test_sh_prefix_6(self):
        assert StockCodeValidator._normalize('600519') == '600519.SH'

    def test_sh_prefix_9(self):
        assert StockCodeValidator._normalize('900001') == '900001.SH'

    def test_bj_prefix_4(self):
        assert StockCodeValidator._normalize('430090') == '430090.BJ'

    def test_bj_prefix_8(self):
        assert StockCodeValidator._normalize('833171') == '833171.BJ'

    def test_already_has_suffix_stripped(self):
        # dots and non-digits are stripped before processing
        assert StockCodeValidator._normalize('000001.SZ') == '000001.SZ'

    def test_short_code_padded(self):
        assert StockCodeValidator._normalize('1') == '000001.SZ'

    def test_whitespace_stripped(self):
        assert StockCodeValidator._normalize('  600519  ') == '600519.SH'


# ---------------------------------------------------------------------------
# Step 2: StockCodeValidator.validate_batch  (mock execute_query)
# ---------------------------------------------------------------------------

class TestValidateBatch:
    def _make_validator(self):
        return StockCodeValidator()

    def test_empty_input_returns_empty(self):
        v = self._make_validator()
        assert v.validate_batch([]) == {}

    @patch('api.services.theme_llm_service.execute_query')
    def test_valid_codes_returned(self, mock_eq):
        mock_eq.return_value = [
            {'stock_code': '000001.SZ', 'stock_name': '平安银行'},
            {'stock_code': '600519.SH', 'stock_name': '贵州茅台'},
        ]
        v = self._make_validator()
        result = v.validate_batch(['000001', '600519'])
        assert result == {
            '000001.SZ': '平安银行',
            '600519.SH': '贵州茅台',
        }
        # verify DB was called once
        mock_eq.assert_called_once()

    @patch('api.services.theme_llm_service.execute_query')
    def test_invalid_codes_not_in_result(self, mock_eq):
        # DB only returns one valid match
        mock_eq.return_value = [{'stock_code': '000001.SZ', 'stock_name': '平安银行'}]
        v = self._make_validator()
        result = v.validate_batch(['000001', '999999'])
        assert '000001.SZ' in result
        assert '999999.SZ' not in result

    @patch('api.services.theme_llm_service.execute_query')
    def test_db_exception_returns_empty(self, mock_eq):
        mock_eq.side_effect = Exception('DB connection failed')
        v = self._make_validator()
        result = v.validate_batch(['000001'])
        assert result == {}

    @patch('api.services.theme_llm_service.execute_query')
    def test_deduplication(self, mock_eq):
        """Duplicate raw codes should only query DB once per normalized code."""
        mock_eq.return_value = [{'stock_code': '000001.SZ', 'stock_name': '平安银行'}]
        v = self._make_validator()
        v.validate_batch(['000001', '000001', '000001'])
        # Should still work correctly
        mock_eq.assert_called_once()


# ---------------------------------------------------------------------------
# Step 3: AKShareConceptFetcher (mock akshare)
# ---------------------------------------------------------------------------

class TestAKShareConceptFetcher:

    @patch('api.services.theme_llm_service.AKShareConceptFetcher._sync_get_all_boards')
    def test_get_all_boards_returns_list(self, mock_sync):
        mock_sync.return_value = ['特高压', '智能电网', '电力设备']
        fetcher = AKShareConceptFetcher()
        result = asyncio.get_event_loop().run_until_complete(fetcher.get_all_boards())
        assert result == ['特高压', '智能电网', '电力设备']
        mock_sync.assert_called_once()

    @patch('api.services.theme_llm_service.AKShareConceptFetcher._sync_get_board_stocks')
    def test_get_board_stocks_returns_list(self, mock_sync):
        mock_sync.return_value = [
            {'code': '000001', 'name': '平安银行'},
            {'code': '600519', 'name': '贵州茅台'},
        ]
        fetcher = AKShareConceptFetcher()
        result = asyncio.get_event_loop().run_until_complete(
            fetcher.get_board_stocks('特高压')
        )
        assert len(result) == 2
        assert result[0]['code'] == '000001'
        mock_sync.assert_called_once_with('特高压')

    def test_sync_get_all_boards_akshare_error_returns_empty(self):
        fetcher = AKShareConceptFetcher()
        with patch('akshare.stock_board_concept_name_em', side_effect=Exception('network error')):
            result = fetcher._sync_get_all_boards()
        assert result == []

    def test_sync_get_board_stocks_akshare_error_returns_empty(self):
        fetcher = AKShareConceptFetcher()
        with patch('akshare.stock_board_concept_cons_em', side_effect=Exception('not found')):
            with patch('time.sleep'):  # avoid actual sleep
                result = fetcher._sync_get_board_stocks('不存在的板块')
        assert result == []


# ---------------------------------------------------------------------------
# Step 4: Pure helper methods
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_json_array(self):
        text = '["特高压", "智能电网"]'
        result = ThemeCreateSkill._extract_json(text)
        assert json.loads(result) == ['特高压', '智能电网']

    def test_json_in_markdown_fence(self):
        text = '```json\n["特高压", "智能电网"]\n```'
        result = ThemeCreateSkill._extract_json(text)
        assert json.loads(result) == ['特高压', '智能电网']

    def test_json_object(self):
        text = 'Some prefix {"selected": [], "excluded_count": 5} trailing text'
        result = ThemeCreateSkill._extract_json(text)
        data = json.loads(result)
        assert 'selected' in data

    def test_nested_json(self):
        text = '{"a": {"b": [1, 2, 3]}, "c": "d"}'
        result = ThemeCreateSkill._extract_json(text)
        data = json.loads(result)
        assert data['a']['b'] == [1, 2, 3]

    def test_no_json_returns_text(self):
        text = 'just plain text with no json'
        result = ThemeCreateSkill._extract_json(text)
        # should return the original text (not raise)
        assert isinstance(result, str)


class TestFuzzyMatchBoards:
    def test_exact_keyword_match(self):
        concepts = ['特高压', '智能电网']
        all_boards = ['特高压', '智能电网', '光伏发电', '风力发电']
        matched = ThemeCreateSkill._fuzzy_match_boards(concepts, all_boards)
        assert '特高压' in matched
        assert '智能电网' in matched
        assert '光伏发电' not in matched

    def test_partial_match(self):
        concepts = ['电网']
        all_boards = ['智能电网', '电网改造', '光伏发电']
        matched = ThemeCreateSkill._fuzzy_match_boards(concepts, all_boards)
        assert '智能电网' in matched
        assert '电网改造' in matched
        assert '光伏发电' not in matched

    def test_no_match(self):
        concepts = ['量子计算']
        all_boards = ['特高压', '智能电网', '光伏发电']
        matched = ThemeCreateSkill._fuzzy_match_boards(concepts, all_boards)
        assert matched == []

    def test_capped_at_8(self):
        concepts = ['电']
        all_boards = [f'电力板块{i}' for i in range(20)]
        matched = ThemeCreateSkill._fuzzy_match_boards(concepts, all_boards)
        assert len(matched) <= 8

    def test_no_duplicates(self):
        concepts = ['特高压', '高压']
        all_boards = ['特高压', '智能电网']
        matched = ThemeCreateSkill._fuzzy_match_boards(concepts, all_boards)
        # '特高压' matches both keywords but should only appear once
        assert matched.count('特高压') == 1


# ---------------------------------------------------------------------------
# Step 5: ThemeCreateSkill LLM helper methods (mock LLM)
# ---------------------------------------------------------------------------

def make_skill_with_mock_llm(llm_responses: list[str]) -> ThemeCreateSkill:
    """Create a ThemeCreateSkill with LLM calls returning pre-defined responses."""
    skill = ThemeCreateSkill.__new__(ThemeCreateSkill)
    skill._fetcher = AKShareConceptFetcher()
    skill._validator = StockCodeValidator()
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = llm_responses
    skill._llm = mock_llm
    return skill


class TestMapConcepts:
    def test_valid_json_list(self):
        skill = make_skill_with_mock_llm(['["特高压", "智能电网", "电力设备"]'])
        result = asyncio.get_event_loop().run_until_complete(
            skill._map_concepts('电网设备')
        )
        assert result == ['特高压', '智能电网', '电力设备']

    def test_json_parse_error_falls_back_to_theme_name(self):
        skill = make_skill_with_mock_llm(['not valid json at all'])
        result = asyncio.get_event_loop().run_until_complete(
            skill._map_concepts('电网设备')
        )
        assert result == ['电网设备']

    def test_non_list_json_falls_back(self):
        skill = make_skill_with_mock_llm(['{"key": "value"}'])
        result = asyncio.get_event_loop().run_until_complete(
            skill._map_concepts('电网设备')
        )
        assert result == ['电网设备']

    def test_markdown_fenced_json(self):
        skill = make_skill_with_mock_llm(['```json\n["特高压"]\n```'])
        result = asyncio.get_event_loop().run_until_complete(
            skill._map_concepts('电网设备')
        )
        assert result == ['特高压']


class TestFilterStocks:
    def _make_stocks(self, codes: list[str]) -> list[dict]:
        return [
            {'stock_code': c, 'stock_name': f'股票{c}', 'boards': ['测试板块'], 'source': 'akshare'}
            for c in codes
        ]

    def test_valid_llm_response(self):
        llm_resp = json.dumps({
            'selected': [
                {'stock_code': '000001.SZ', 'stock_name': '平安银行', 'relevance': 'high', 'reason': '核心业务'},
                {'stock_code': '600519.SH', 'stock_name': '贵州茅台', 'relevance': 'medium', 'reason': '间接受益'},
            ],
            'excluded_count': 3,
            'exclusion_summary': '排除了弱相关标的',
        })
        skill = make_skill_with_mock_llm([llm_resp])
        stocks = self._make_stocks(['000001.SZ', '600519.SH', '000002.SZ'])
        result = asyncio.get_event_loop().run_until_complete(
            skill._filter_stocks('电网设备', stocks)
        )
        assert len(result) == 2
        assert result[0]['stock_code'] == '000001.SZ'
        assert result[0]['relevance'] == 'high'
        assert result[0]['source'] == 'akshare'

    def test_empty_stocks_returns_empty(self):
        skill = make_skill_with_mock_llm([])
        result = asyncio.get_event_loop().run_until_complete(
            skill._filter_stocks('电网设备', [])
        )
        assert result == []

    def test_llm_parse_error_returns_fallback(self):
        skill = make_skill_with_mock_llm(['invalid json response'])
        stocks = self._make_stocks(['000001.SZ', '600519.SH'])
        result = asyncio.get_event_loop().run_until_complete(
            skill._filter_stocks('电网设备', stocks)
        )
        # fallback: returns first 50 stocks with medium relevance
        assert len(result) == 2
        assert all(s['relevance'] == 'medium' for s in result)

    def test_boards_preserved_from_original(self):
        llm_resp = json.dumps({
            'selected': [{'stock_code': '000001.SZ', 'stock_name': '平安银行', 'relevance': 'high', 'reason': ''}],
            'excluded_count': 0, 'exclusion_summary': '',
        })
        skill = make_skill_with_mock_llm([llm_resp])
        stocks = [{'stock_code': '000001.SZ', 'stock_name': '平安银行', 'boards': ['特高压', '智能电网'], 'source': 'akshare'}]
        result = asyncio.get_event_loop().run_until_complete(
            skill._filter_stocks('电网设备', stocks)
        )
        assert result[0]['boards'] == ['特高压', '智能电网']


class TestSupplementStocks:
    def test_valid_llm_response(self):
        llm_resp = json.dumps({
            'supplements': [
                {'stock_code': '600905.SH', 'stock_name': '三峡能源', 'reason': '电网相关'},
            ]
        })
        skill = make_skill_with_mock_llm([llm_resp])
        result = asyncio.get_event_loop().run_until_complete(
            skill._supplement_stocks('电网设备', ['000001.SZ'])
        )
        assert len(result) == 1
        assert result[0]['stock_code'] == '600905.SH'

    def test_llm_parse_error_returns_empty(self):
        skill = make_skill_with_mock_llm(['not json'])
        result = asyncio.get_event_loop().run_until_complete(
            skill._supplement_stocks('电网设备', [])
        )
        assert result == []


# ---------------------------------------------------------------------------
# Step 6: ThemeCreateSkill.stream full flow (mock everything)
# ---------------------------------------------------------------------------

class TestThemeCreateSkillStream:

    def _collect_events(self, skill: ThemeCreateSkill, theme_name: str) -> list[dict]:
        """Run stream() and collect all events into a list."""
        events = []

        async def _run():
            async for event in skill.stream(theme_name=theme_name):
                events.append(event)

        asyncio.get_event_loop().run_until_complete(_run())
        return events

    def _make_full_mock_skill(self) -> ThemeCreateSkill:
        """Create skill with all external calls mocked."""
        skill = ThemeCreateSkill.__new__(ThemeCreateSkill)

        # Mock fetcher
        mock_fetcher = MagicMock()
        mock_fetcher.get_all_boards = AsyncMock(return_value=['特高压', '智能电网', '光伏发电'])
        mock_fetcher.get_board_stocks = AsyncMock(return_value=[
            {'code': '000001', 'name': '平安银行'},
            {'code': '600905', 'name': '三峡能源'},
        ])
        skill._fetcher = mock_fetcher

        # Mock validator
        mock_validator = MagicMock()
        mock_validator.validate_batch.return_value = {
            '000001.SZ': '平安银行',
            '600905.SH': '三峡能源',
        }
        skill._validator = mock_validator

        # Mock LLM: 3 calls in sequence
        filter_resp = json.dumps({
            'selected': [
                {'stock_code': '000001.SZ', 'stock_name': '平安银行', 'relevance': 'high', 'reason': '直接受益'},
            ],
            'excluded_count': 1, 'exclusion_summary': '排除弱相关',
        })
        supplement_resp = json.dumps({
            'supplements': [
                {'stock_code': '600905.SH', 'stock_name': '三峡能源', 'reason': 'AI补充'},
            ]
        })
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = [
            '["特高压", "智能电网"]',  # phase 1: concept mapping
            filter_resp,               # phase 4: filter
            supplement_resp,           # phase 5: supplement
        ]
        skill._llm = mock_llm

        return skill

    def test_stream_completes_with_done_event(self):
        skill = self._make_full_mock_skill()
        events = self._collect_events(skill, '电网设备')
        types = [e['type'] for e in events]
        assert 'done' in types
        assert 'error' not in types

    def test_stream_starts_with_start_event(self):
        skill = self._make_full_mock_skill()
        events = self._collect_events(skill, '电网设备')
        assert events[0]['type'] == 'start'

    def test_stream_has_concept_mapping_event(self):
        skill = self._make_full_mock_skill()
        events = self._collect_events(skill, '电网设备')
        concept_events = [e for e in events if e['type'] == 'concept_mapping']
        assert len(concept_events) == 1
        assert '特高压' in concept_events[0]['concepts']

    def test_stream_has_candidate_list_event(self):
        skill = self._make_full_mock_skill()
        events = self._collect_events(skill, '电网设备')
        candidate_events = [e for e in events if e['type'] == 'candidate_list']
        assert len(candidate_events) == 1
        stocks = candidate_events[0]['stocks']
        assert len(stocks) >= 1

    def test_stream_candidate_list_has_required_fields(self):
        skill = self._make_full_mock_skill()
        events = self._collect_events(skill, '电网设备')
        stocks = next(e['stocks'] for e in events if e['type'] == 'candidate_list')
        for stock in stocks:
            assert 'stock_code' in stock
            assert 'stock_name' in stock
            assert 'source' in stock
            assert 'relevance' in stock
            assert 'reason' in stock

    def test_stream_no_duplicate_codes_in_candidate_list(self):
        skill = self._make_full_mock_skill()
        events = self._collect_events(skill, '电网设备')
        stocks = next(e['stocks'] for e in events if e['type'] == 'candidate_list')
        codes = [s['stock_code'] for s in stocks]
        assert len(codes) == len(set(codes)), 'Duplicate stock codes found in candidate list'

    def test_stream_error_event_on_exception(self):
        """If an unexpected error occurs, stream should yield an error event, not raise."""
        skill = ThemeCreateSkill.__new__(ThemeCreateSkill)
        skill._fetcher = MagicMock()
        skill._fetcher.get_all_boards = AsyncMock(side_effect=RuntimeError('network failure'))
        skill._validator = StockCodeValidator()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = '["特高压"]'
        skill._llm = mock_llm

        events = self._collect_events(skill, '电网设备')
        types = [e['type'] for e in events]
        assert 'error' in types

    def test_stream_respects_max_candidates(self):
        """Candidate list should be capped at max_candidates."""
        skill = self._make_full_mock_skill()
        # Make fetcher return many stocks
        skill._fetcher.get_board_stocks = AsyncMock(return_value=[
            {'code': str(i).zfill(6), 'name': f'股票{i}'} for i in range(1, 100)
        ])
        skill._validator.validate_batch.return_value = {
            f'{str(i).zfill(6)}.SZ': f'股票{i}' for i in range(1, 100)
        }
        # LLM filter returns all of them
        many_selected = [
            {'stock_code': f'{str(i).zfill(6)}.SZ', 'stock_name': f'股票{i}',
             'relevance': 'high', 'reason': ''}
            for i in range(1, 51)
        ]
        skill._llm.generate.side_effect = [
            '["特高压"]',
            json.dumps({'selected': many_selected, 'excluded_count': 0, 'exclusion_summary': ''}),
            json.dumps({'supplements': []}),
        ]

        events = []

        async def _run():
            async for event in skill.stream(theme_name='测试', max_candidates=10):
                events.append(event)

        asyncio.get_event_loop().run_until_complete(_run())
        stocks = next(e['stocks'] for e in events if e['type'] == 'candidate_list')
        assert len(stocks) <= 10
