"""
Unit tests for concept_board_fetcher (daily sync task).
Tests cover:
  - _normalize_code: various input formats
  - fetch_board_members: AKShare mock
  - upsert_concept_members: execute_many mock
  - run_sync: integration of steps, error handling
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from data_analyst.fetchers.concept_board_fetcher import _normalize_code, run_sync, upsert_concept_members


class TestNormalizeCode(unittest.TestCase):

    def test_sz_prefix_0(self):
        self.assertEqual(_normalize_code('000001'), '000001.SZ')

    def test_sz_prefix_3(self):
        self.assertEqual(_normalize_code('300750'), '300750.SZ')

    def test_sh_prefix_6(self):
        self.assertEqual(_normalize_code('600519'), '600519.SH')

    def test_sh_prefix_9(self):
        self.assertEqual(_normalize_code('900001'), '900001.SH')

    def test_bj_prefix_4(self):
        self.assertEqual(_normalize_code('430047'), '430047.BJ')

    def test_pad_short_code(self):
        self.assertEqual(_normalize_code('1'), '000001.SZ')

    def test_strip_non_digits(self):
        self.assertEqual(_normalize_code('600519.SH'), '600519.SH')

    def test_already_six_digits(self):
        self.assertEqual(_normalize_code('002594'), '002594.SZ')


class TestFetchBoardMembers(unittest.TestCase):

    def test_returns_normalized_codes(self):
        mock_df = MagicMock()
        mock_df.iterrows.return_value = [
            (0, {'代码': '600519', '名称': '贵州茅台'}),
            (1, {'代码': '000001', '名称': '平安银行'}),
        ]
        with patch('akshare.stock_board_concept_cons_em', return_value=mock_df):
            from data_analyst.fetchers.concept_board_fetcher import fetch_board_members
            result = fetch_board_members('白酒')
        self.assertEqual(len(result), 2)
        codes = [r['stock_code'] for r in result]
        self.assertIn('600519.SH', codes)
        self.assertIn('000001.SZ', codes)

    def test_akshare_exception_returns_empty(self):
        with patch('akshare.stock_board_concept_cons_em', side_effect=Exception('network error')):
            from data_analyst.fetchers.concept_board_fetcher import fetch_board_members
            result = fetch_board_members('白酒')
        self.assertEqual(result, [])


class TestUpsertConceptMembers(unittest.TestCase):

    def test_calls_execute_many(self):
        rows = [
            {'stock_code': '600519.SH', 'stock_name': '贵州茅台', 'concept_name': '白酒', 'updated_at': datetime.utcnow()},
            {'stock_code': '000858.SZ', 'stock_name': '五粮液', 'concept_name': '白酒', 'updated_at': datetime.utcnow()},
        ]
        with patch('data_analyst.fetchers.concept_board_fetcher.execute_many') as mock_em:
            count = upsert_concept_members(rows)
        self.assertEqual(count, 2)
        mock_em.assert_called_once()
        # Check params shape: list of 4-tuples
        call_args = mock_em.call_args
        params = call_args[0][1]
        self.assertEqual(len(params), 2)
        self.assertEqual(len(params[0]), 4)

    def test_empty_rows_returns_zero(self):
        with patch('data_analyst.fetchers.concept_board_fetcher.execute_many') as mock_em:
            count = upsert_concept_members([])
        self.assertEqual(count, 0)
        mock_em.assert_not_called()


class TestRunSync(unittest.TestCase):

    def test_full_sync_happy_path(self):
        """run_sync should iterate boards, fetch members, upsert."""
        mock_df_boards = MagicMock()
        mock_df_boards.__getitem__ = MagicMock(return_value=MagicMock(tolist=MagicMock(return_value=['白酒', '特高压'])))

        mock_df_members = MagicMock()
        mock_df_members.iterrows.return_value = [
            (0, {'代码': '600519', '名称': '贵州茅台'}),
        ]

        with patch('akshare.stock_board_concept_name_em', return_value=mock_df_boards), \
             patch('akshare.stock_board_concept_cons_em', return_value=mock_df_members), \
             patch('data_analyst.fetchers.concept_board_fetcher.execute_many') as mock_em, \
             patch('time.sleep'):
            result = run_sync(limit=2, sleep_between=0)

        self.assertEqual(result['board_count'], 2)
        self.assertGreater(result['stock_count'], 0)
        self.assertEqual(result['error_count'], 0)

    def test_empty_boards_returns_zero(self):
        mock_df_boards = MagicMock()
        mock_df_boards.__getitem__ = MagicMock(return_value=MagicMock(tolist=MagicMock(return_value=[])))

        with patch('akshare.stock_board_concept_name_em', return_value=mock_df_boards):
            result = run_sync()

        self.assertEqual(result['board_count'], 0)
        self.assertEqual(result['stock_count'], 0)

    def test_akshare_board_list_failure_returns_zero(self):
        with patch('akshare.stock_board_concept_name_em', side_effect=Exception('api error')):
            result = run_sync()
        self.assertEqual(result['board_count'], 0)

    def test_limit_restricts_boards(self):
        mock_df_boards = MagicMock()
        mock_df_boards.__getitem__ = MagicMock(
            return_value=MagicMock(tolist=MagicMock(return_value=[f'board_{i}' for i in range(100)]))
        )
        mock_df_members = MagicMock()
        mock_df_members.iterrows.return_value = []

        with patch('akshare.stock_board_concept_name_em', return_value=mock_df_boards), \
             patch('akshare.stock_board_concept_cons_em', return_value=mock_df_members), \
             patch('data_analyst.fetchers.concept_board_fetcher.execute_many'), \
             patch('time.sleep'):
            result = run_sync(limit=5, sleep_between=0)

        self.assertEqual(result['board_count'], 5)


if __name__ == '__main__':
    unittest.main()
