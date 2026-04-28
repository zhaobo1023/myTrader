# -*- coding: utf-8 -*-
"""
Unit tests for data_analyst/factors/extended_factor_calculator.py
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


class TestCalcPriceVolumeFactorsVectorized(unittest.TestCase):

    def _make_df(self, n_stocks=3, n_days=80):
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=n_days, freq='B')
        rows = []
        for i in range(n_stocks):
            code = f'{i:06d}.SH'
            close = 10 + np.cumsum(np.random.randn(n_days) * 0.02)
            for j, d in enumerate(dates):
                rows.append({
                    'stock_code': code,
                    'trade_date': d,
                    'open_price': close[j] * 0.99,
                    'high_price': close[j] * 1.02,
                    'low_price': close[j] * 0.98,
                    'close_price': close[j],
                    'volume': 1000000 + np.random.randint(-100000, 100000),
                    'amount': 10000000 + np.random.randint(-1000000, 1000000),
                    'turnover_rate': 1.0 + np.random.rand(),
                })
        return pd.DataFrame(rows).sort_values(['stock_code', 'trade_date']).reset_index(drop=True)

    def test_output_columns(self):
        from data_analyst.factors.extended_factor_calculator import calc_price_volume_factors_vectorized
        df = self._make_df()
        result = calc_price_volume_factors_vectorized(df)
        expected = ['mom_5', 'mom_10', 'reversal_1', 'turnover_20_mean',
                    'amihud_illiquidity', 'high_low_ratio', 'volume_ratio_20']
        for col in expected:
            self.assertIn(col, result.columns)

    def test_mom_5_values(self):
        """mom_5 should be 5-day pct_change of close_price"""
        from data_analyst.factors.extended_factor_calculator import calc_price_volume_factors_vectorized
        df = self._make_df(n_stocks=1)
        result = calc_price_volume_factors_vectorized(df)
        valid = result['mom_5'].dropna()
        self.assertGreater(len(valid), 0)
        # Manually check one value
        close = result['close_price'].values
        expected = (close[5] - close[0]) / close[0]
        actual = result['mom_5'].iloc[5]
        self.assertAlmostEqual(actual, expected, places=10)

    def test_reversal_1_sign(self):
        """reversal_1 should be negative of 1-day return"""
        from data_analyst.factors.extended_factor_calculator import calc_price_volume_factors_vectorized
        df = self._make_df(n_stocks=1)
        result = calc_price_volume_factors_vectorized(df)
        close = result['close_price'].values
        for i in range(1, min(10, len(result))):
            if not np.isnan(result['reversal_1'].iloc[i]):
                expected = -(close[i] - close[i-1]) / close[i-1]
                self.assertAlmostEqual(result['reversal_1'].iloc[i], expected, places=10)

    def test_row_count_preserved(self):
        """Output should have same row count as input"""
        from data_analyst.factors.extended_factor_calculator import calc_price_volume_factors_vectorized
        df = self._make_df()
        result = calc_price_volume_factors_vectorized(df)
        self.assertEqual(len(result), len(df))


class TestCalcFinancialFactorsVectorized(unittest.TestCase):

    def test_basic_merge(self):
        from data_analyst.factors.extended_factor_calculator import calc_financial_factors_vectorized

        dates = pd.date_range('2024-01-01', periods=30, freq='B')
        daily = pd.DataFrame({
            'stock_code': ['A'] * 30,
            'trade_date': dates,
        })

        fin = pd.DataFrame({
            'stock_code': ['A'] * 8,
            'report_date': pd.to_datetime([
                '2022-03-31', '2022-06-30', '2022-09-30', '2022-12-31',
                '2023-03-31', '2023-06-30', '2023-09-30', '2023-12-31',
            ]),
            'roe': [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
            'net_profit': [100, 110, 120, 130, 140, 150, 160, 170],
            'revenue': [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700],
            'gross_margin': [30.0, 31.0, 32.0, 33.0, 34.0, 35.0, 36.0, 37.0],
            'operating_cashflow': [50, 55, 60, 65, 70, 75, 80, 85],
            'eps': [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
            'total_equity': [100, 100, 100, 100, 100, 100, 100, 100],
        })

        result = calc_financial_factors_vectorized(daily, fin)
        self.assertIn('roe_ttm', result.columns)
        self.assertIn('gross_margin', result.columns)
        # All rows should have latest financial data (2023-12-31)
        self.assertEqual(result['roe_ttm'].dropna().iloc[0], 17.0)

    def test_empty_financial(self):
        from data_analyst.factors.extended_factor_calculator import calc_financial_factors_vectorized

        daily = pd.DataFrame({
            'stock_code': ['A'] * 10,
            'trade_date': pd.date_range('2024-01-01', periods=10, freq='B'),
        })
        fin = pd.DataFrame()
        result = calc_financial_factors_vectorized(daily, fin)
        self.assertTrue(result['roe_ttm'].isna().all())


class TestLoadDataBatched(unittest.TestCase):

    @patch('data_analyst.factors.extended_factor_calculator.execute_query')
    def test_batched_loading(self, mock_query):
        from data_analyst.factors.extended_factor_calculator import load_daily_data_batched

        mock_query.return_value = [
            {'stock_code': 'A', 'trade_date': '2024-01-01',
             'open_price': 10, 'high_price': 11, 'low_price': 9,
             'close_price': 10.5, 'volume': 1000, 'amount': 10000,
             'turnover_rate': 1.0},
        ]

        codes = [f'{i:06d}.SH' for i in range(5)]
        result = load_daily_data_batched(codes, '2024-01-01', '2024-12-31', batch_size=2)
        self.assertGreater(len(result), 0)
        # 5 codes with batch_size=2 = 3 batches
        self.assertEqual(mock_query.call_count, 3)

    @patch('data_analyst.factors.extended_factor_calculator.execute_query')
    def test_empty_result(self, mock_query):
        from data_analyst.factors.extended_factor_calculator import load_daily_data_batched
        mock_query.return_value = []
        result = load_daily_data_batched(['A'], '2024-01-01', '2024-12-31')
        self.assertTrue(result.empty)


class TestSaveFactorsDataframe(unittest.TestCase):

    @patch('data_analyst.factors.extended_factor_calculator.get_dual_connections')
    def test_save_basic(self, mock_dual):
        from data_analyst.factors.extended_factor_calculator import save_factors_dataframe

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_dual.return_value = (mock_conn, None)

        df = pd.DataFrame({
            'stock_code': ['A', 'B'],
            'trade_date': pd.to_datetime(['2024-01-01', '2024-01-01']),
            'mom_5': [0.01, 0.02],
            'mom_10': [0.03, 0.04],
            'reversal_1': [-0.01, -0.02],
            'turnover_20_mean': [1.0, 2.0],
            'amihud_illiquidity': [0.001, 0.002],
            'high_low_ratio': [0.02, 0.03],
            'volume_ratio_20': [1.1, 0.9],
            'roe_ttm': [10.0, np.nan],
            'gross_margin': [30.0, np.nan],
            'net_profit_growth': [0.1, np.nan],
            'revenue_growth': [0.2, np.nan],
        })

        result = save_factors_dataframe(df, env='online')
        self.assertEqual(result, 2)
        mock_cursor.executemany.assert_called_once()


if __name__ == '__main__':
    unittest.main()
