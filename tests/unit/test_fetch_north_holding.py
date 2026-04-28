# -*- coding: utf-8 -*-
"""
Unit tests for scripts/fetch_north_holding.py
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


class TestNormalizeCode(unittest.TestCase):
    def test_sh_code(self):
        from scripts.fetch_north_holding import _normalize_code
        self.assertEqual(_normalize_code('600519'), '600519.SH')

    def test_sz_code(self):
        from scripts.fetch_north_holding import _normalize_code
        self.assertEqual(_normalize_code('000001'), '000001.SZ')

    def test_bj_code(self):
        from scripts.fetch_north_holding import _normalize_code
        self.assertEqual(_normalize_code('430047'), '430047.BJ')

    def test_gem_code(self):
        from scripts.fetch_north_holding import _normalize_code
        self.assertEqual(_normalize_code('300750'), '300750.SZ')


class TestSafeFloat(unittest.TestCase):
    def test_normal(self):
        from scripts.fetch_north_holding import _safe_float
        self.assertEqual(_safe_float(100.5), 100.5)

    def test_none(self):
        from scripts.fetch_north_holding import _safe_float
        self.assertEqual(_safe_float(None), 0.0)

    def test_invalid(self):
        from scripts.fetch_north_holding import _safe_float
        self.assertEqual(_safe_float("abc"), 0.0)


class TestFetchByDateRange(unittest.TestCase):

    @patch('scripts.fetch_north_holding._upsert_rows')
    @patch('scripts.fetch_north_holding.ak')
    @patch('scripts.fetch_north_holding.get_trading_dates')
    @patch('scripts.fetch_north_holding.time')
    def test_happy_path(self, mock_time, mock_dates, mock_ak, mock_upsert):
        import pandas as pd
        from scripts.fetch_north_holding import fetch_by_date_range

        mock_dates.return_value = ['2024-08-15']

        df = pd.DataFrame({
            '持股日期': ['2024-08-15'],
            '股票代码': ['600519'],
            '股票简称': ['test'],
            '当日收盘价': [1420.0],
            '当日涨跌幅': [0.5],
            '持股数量': [82000000],
            '持股市值': [116000000000],
            '持股数量占发行股百分比': [6.55],
            '持股市值变化-1日': [500000000],
            '持股市值变化-5日': [200000000],
            '持股市值变化-10日': [100000000],
        })
        mock_ak.stock_hsgt_stock_statistics_em.return_value = df

        result = fetch_by_date_range('2024-08-15', '2024-08-15')
        self.assertEqual(result, 1)
        mock_upsert.assert_called_once()
        rows = mock_upsert.call_args[0][0]
        self.assertEqual(rows[0][0], '600519.SH')

    @patch('scripts.fetch_north_holding._upsert_rows')
    @patch('scripts.fetch_north_holding.ak')
    @patch('scripts.fetch_north_holding.get_trading_dates')
    @patch('scripts.fetch_north_holding.time')
    def test_api_failure_continues(self, mock_time, mock_dates, mock_ak, mock_upsert):
        from scripts.fetch_north_holding import fetch_by_date_range

        mock_dates.return_value = ['2024-08-15']
        mock_ak.stock_hsgt_stock_statistics_em.side_effect = Exception("API error")

        result = fetch_by_date_range('2024-08-15', '2024-08-15')
        self.assertEqual(result, 0)
        mock_upsert.assert_not_called()


class TestFetchOneStock(unittest.TestCase):

    @patch('scripts.fetch_north_holding._upsert_rows')
    @patch('scripts.fetch_north_holding.ak')
    def test_single_stock(self, mock_ak, mock_upsert):
        import pandas as pd
        from scripts.fetch_north_holding import fetch_one_stock

        df = pd.DataFrame({
            '持股日期': ['2024-08-15', '2024-08-16'],
            '当日收盘价': [1420.0, 1431.0],
            '当日涨跌幅': [0.5, 0.3],
            '持股数量': [82000000, 82300000],
            '持股市值': [116000000000, 117000000000],
            '持股数量占A股百分比': [6.55, 6.55],
            '今日增持股数': [200000, 300000],
            '今日增持资金': [280000000, 430000000],
            '今日持股市值变化': [500000000, 1000000000],
        })
        mock_ak.stock_hsgt_individual_em.return_value = df

        result = fetch_one_stock('600519.SH', '2024-08-15')
        self.assertEqual(result, 2)
        mock_upsert.assert_called_once()

    @patch('scripts.fetch_north_holding.ak')
    def test_api_failure_returns_zero(self, mock_ak):
        from scripts.fetch_north_holding import fetch_one_stock

        mock_ak.stock_hsgt_individual_em.side_effect = Exception("error")
        result = fetch_one_stock('600519.SH')
        self.assertEqual(result, 0)


class TestGetLatestDate(unittest.TestCase):

    @patch('scripts.fetch_north_holding.execute_query')
    def test_returns_date(self, mock_query):
        from scripts.fetch_north_holding import get_latest_date
        mock_query.return_value = [{'max_date': '2024-08-16'}]
        self.assertEqual(get_latest_date(), '2024-08-16')

    @patch('scripts.fetch_north_holding.execute_query')
    def test_empty_table(self, mock_query):
        from scripts.fetch_north_holding import get_latest_date
        mock_query.return_value = [{'max_date': None}]
        self.assertEqual(get_latest_date(), '')


if __name__ == '__main__':
    unittest.main()
