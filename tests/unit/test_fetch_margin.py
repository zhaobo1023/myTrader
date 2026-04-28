# -*- coding: utf-8 -*-
"""
Unit tests for scripts/fetch_margin.py
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


class TestSafeFloat(unittest.TestCase):
    def test_normal_float(self):
        from scripts.fetch_margin import _safe_float
        self.assertEqual(_safe_float(123.45), 123.45)

    def test_none_returns_default(self):
        from scripts.fetch_margin import _safe_float
        self.assertEqual(_safe_float(None), 0.0)

    def test_string_number(self):
        from scripts.fetch_margin import _safe_float
        self.assertEqual(_safe_float("100.5"), 100.5)

    def test_invalid_string(self):
        from scripts.fetch_margin import _safe_float
        self.assertEqual(_safe_float("abc"), 0.0)

    def test_custom_default(self):
        from scripts.fetch_margin import _safe_float
        self.assertEqual(_safe_float(None, -1.0), -1.0)


class TestFetchOneDay(unittest.TestCase):
    """Test fetch_one_day with mocked AKShare APIs."""

    @patch('scripts.fetch_margin.execute_many')
    @patch('scripts.fetch_margin.ak')
    @patch('scripts.fetch_margin.time')
    def test_sse_and_szse_combined(self, mock_time, mock_ak, mock_execute_many):
        import pandas as pd
        from scripts.fetch_margin import fetch_one_day

        # Mock SSE response
        df_sse = pd.DataFrame({
            '信用交易日期': ['20260424'],
            '标的证券代码': ['600519'],
            '标的证券简称': ['test'],
            '融资余额': [1000000],
            '融资买入额': [50000],
            '融资偿还额': [30000],
            '融券余量': [10000],
            '融券卖出量': [5000],
            '融券偿还量': [3000],
        })
        mock_ak.stock_margin_detail_sse.return_value = df_sse

        # Mock SZSE response
        df_szse = pd.DataFrame({
            '证券代码': ['000001'],
            '证券简称': ['test_sz'],
            '融资买入额': [80000],
            '融资余额': [2000000],
            '融券卖出量': [6000],
            '融券余量': [8000],
            '融券余额': [15000],
            '融资融券余额': [2015000],
        })
        mock_ak.stock_margin_detail_szse.return_value = df_szse

        result = fetch_one_day('2026-04-24')
        self.assertEqual(result, 2)
        mock_execute_many.assert_called_once()
        rows = mock_execute_many.call_args[0][1]
        codes = [r[0] for r in rows]
        self.assertIn('600519.SH', codes)
        self.assertIn('000001.SZ', codes)

    @patch('scripts.fetch_margin.execute_many')
    @patch('scripts.fetch_margin.ak')
    @patch('scripts.fetch_margin.time')
    def test_both_apis_fail_returns_zero(self, mock_time, mock_ak, mock_execute_many):
        from scripts.fetch_margin import fetch_one_day

        mock_ak.stock_margin_detail_sse.side_effect = Exception("API error")
        mock_ak.stock_margin_detail_szse.side_effect = Exception("API error")

        result = fetch_one_day('2026-04-24')
        self.assertEqual(result, 0)
        mock_execute_many.assert_not_called()

    @patch('scripts.fetch_margin.execute_many')
    @patch('scripts.fetch_margin.ak')
    @patch('scripts.fetch_margin.time')
    def test_empty_dataframes_returns_zero(self, mock_time, mock_ak, mock_execute_many):
        import pandas as pd
        from scripts.fetch_margin import fetch_one_day

        mock_ak.stock_margin_detail_sse.return_value = pd.DataFrame()
        mock_ak.stock_margin_detail_szse.return_value = pd.DataFrame()

        result = fetch_one_day('2026-04-24')
        self.assertEqual(result, 0)


class TestFetchByDateRange(unittest.TestCase):

    @patch('scripts.fetch_margin.fetch_one_day')
    @patch('scripts.fetch_margin.get_trading_dates')
    def test_iterates_all_dates(self, mock_dates, mock_fetch_day):
        from scripts.fetch_margin import fetch_by_date_range

        mock_dates.return_value = ['2026-04-22', '2026-04-23', '2026-04-24']
        mock_fetch_day.return_value = 100

        result = fetch_by_date_range('2026-04-22', '2026-04-24')
        self.assertEqual(result, 300)
        self.assertEqual(mock_fetch_day.call_count, 3)


class TestGetLatestDate(unittest.TestCase):

    @patch('scripts.fetch_margin.execute_query')
    def test_returns_date_string(self, mock_query):
        from scripts.fetch_margin import get_latest_date
        mock_query.return_value = [{'max_date': '2026-04-24'}]
        self.assertEqual(get_latest_date(), '2026-04-24')

    @patch('scripts.fetch_margin.execute_query')
    def test_returns_empty_when_no_data(self, mock_query):
        from scripts.fetch_margin import get_latest_date
        mock_query.return_value = [{'max_date': None}]
        self.assertEqual(get_latest_date(), '')


if __name__ == '__main__':
    unittest.main()
