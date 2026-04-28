# -*- coding: utf-8 -*-
"""
Unit tests for data_analyst/indicators/rps_calculator.py
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


class TestCalcRps(unittest.TestCase):

    def setUp(self):
        from data_analyst.indicators.rps_calculator import RPSCalculator
        self.calc = RPSCalculator(windows=[20])

    def test_basic_ranking(self):
        """RPS should rank stocks cross-sectionally within each date"""
        dates = pd.date_range('2024-01-01', periods=30, freq='B')
        rows = []
        # Stock A: rising, Stock B: flat, Stock C: falling
        for i, d in enumerate(dates):
            rows.append({'stock_code': 'A', 'trade_date': d, 'close': 10 + i * 0.5})
            rows.append({'stock_code': 'B', 'trade_date': d, 'close': 10.0})
            rows.append({'stock_code': 'C', 'trade_date': d, 'close': 10 - i * 0.5})

        df = pd.DataFrame(rows)
        rps = self.calc.calc_rps(df, window=20)
        df['rps'] = rps

        # At the last date, Stock A should have highest RPS, C lowest
        last_date = dates[-1]
        last = df[df['trade_date'] == last_date].set_index('stock_code')
        self.assertGreater(last.loc['A', 'rps'], last.loc['C', 'rps'])

    def test_nan_for_insufficient_data(self):
        """RPS should be NaN when not enough history for pct_change"""
        dates = pd.date_range('2024-01-01', periods=10, freq='B')
        rows = [{'stock_code': 'A', 'trade_date': d, 'close': 10.0} for d in dates]
        df = pd.DataFrame(rows)
        rps = self.calc.calc_rps(df, window=20)
        self.assertTrue(rps.isna().all())


class TestCalcRpsSlope(unittest.TestCase):

    def setUp(self):
        from data_analyst.indicators.rps_calculator import RPSCalculator
        self.calc = RPSCalculator()

    def test_linear_increasing_rps(self):
        """Stock with rising RPS should have higher slope Z-score than falling"""
        n_days = 50
        dates = pd.date_range('2024-01-01', periods=n_days, freq='B')
        df = pd.concat([
            pd.DataFrame({
                'stock_code': ['A'] * n_days,
                'trade_date': dates,
                'rps_250': np.linspace(10, 90, n_days),
            }),
            pd.DataFrame({
                'stock_code': ['B'] * n_days,
                'trade_date': dates,
                'rps_250': np.linspace(90, 10, n_days),
            }),
        ], ignore_index=True)
        df = df.sort_values(['stock_code', 'trade_date']).reset_index(drop=True)
        slope = self.calc.calc_rps_slope(df['rps_250'], df['trade_date'], df['stock_code'])
        df['slope'] = slope.values
        last = df.groupby('stock_code')['slope'].last()
        self.assertGreater(last['A'], last['B'])

    def test_constant_rps_zero_slope(self):
        """Slope of constant RPS should be zero"""
        n_days = 50
        df = pd.DataFrame({
            'stock_code': ['A'] * n_days + ['B'] * n_days,
            'trade_date': list(pd.date_range('2024-01-01', periods=n_days, freq='B')) * 2,
            'rps_250': [50.0] * n_days + [50.0] * n_days,
        })
        slope = self.calc.calc_rps_slope(df['rps_250'], df['trade_date'], df['stock_code'])
        valid = slope.dropna()
        if len(valid) > 0:
            self.assertTrue((valid.abs() < 1e-10).all())

    def test_matches_scipy_linregress(self):
        """Vectorized slope should match scipy linregress results"""
        from scipy import stats

        np.random.seed(42)
        n_stocks = 10
        n_days = 60

        rows = []
        for i in range(n_stocks):
            code = f'{i:06d}.SH'
            for j in range(n_days):
                rows.append({
                    'stock_code': code,
                    'trade_date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=j),
                    'rps_250': np.random.rand() * 100,
                })
        df = pd.DataFrame(rows).sort_values(['stock_code', 'trade_date']).reset_index(drop=True)

        # New vectorized
        slope_new = self.calc.calc_rps_slope(df['rps_250'], df['trade_date'], df['stock_code'])

        # Old scipy approach
        window = 20
        def _slope_old(y):
            valid = y.dropna()
            if len(valid) < window:
                return np.nan
            x_vals = np.arange(len(valid))
            s, _, _, _, _ = stats.linregress(x_vals, valid.values)
            return s

        df2 = df.copy()
        df2['slope_raw'] = df2.groupby('stock_code')['rps_250'].transform(
            lambda x: x.rolling(window=window, min_periods=window).apply(_slope_old, raw=False)
        )

        def _zscore(x):
            s = x.std()
            if s > 0:
                return (x - x.mean()) / s
            return pd.Series(np.nan, index=x.index)

        df2['slope_old'] = df2.groupby('trade_date')['slope_raw'].transform(_zscore)

        df['slope_new'] = slope_new.values
        df['slope_old'] = df2['slope_old'].values

        mask = df['slope_new'].notna() & df['slope_old'].notna()
        self.assertGreater(mask.sum(), 0)
        max_diff = (df.loc[mask, 'slope_new'] - df.loc[mask, 'slope_old']).abs().max()
        self.assertLess(max_diff, 1e-10)


class TestCalculate(unittest.TestCase):

    def test_output_columns(self):
        """calculate() should produce all expected output columns"""
        from data_analyst.indicators.rps_calculator import RPSCalculator

        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=280, freq='B')
        rows = []
        for code in ['A', 'B', 'C']:
            close = 10 + np.cumsum(np.random.randn(280) * 0.02)
            for d, c in zip(dates, close):
                rows.append({'stock_code': code, 'trade_date': d, 'close': c})

        df = pd.DataFrame(rows)
        calc = RPSCalculator()
        result = calc.calculate(df)

        expected_cols = ['rps_20', 'rps_60', 'rps_120', 'rps_250', 'rps_slope']
        for col in expected_cols:
            self.assertIn(col, result.columns)

    def test_rps_range(self):
        """RPS values should be between 0 and 100"""
        from data_analyst.indicators.rps_calculator import RPSCalculator

        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=280, freq='B')
        rows = []
        for i in range(5):
            close = 10 + np.cumsum(np.random.randn(280) * 0.02)
            for d, c in zip(dates, close):
                rows.append({'stock_code': f'{i:06d}.SH', 'trade_date': d, 'close': c})

        df = pd.DataFrame(rows)
        calc = RPSCalculator()
        result = calc.calculate(df)

        for col in ['rps_20', 'rps_60', 'rps_120', 'rps_250']:
            valid = result[col].dropna()
            if len(valid) > 0:
                self.assertGreaterEqual(valid.min(), 0)
                self.assertLessEqual(valid.max(), 100)


class TestLoadAllDataBatched(unittest.TestCase):

    @patch('data_analyst.indicators.rps_calculator.execute_query')
    def test_batched_loading(self, mock_query):
        """Should load data in batches and concat"""
        from data_analyst.indicators.rps_calculator import _load_all_data_batched

        mock_query.return_value = [
            {'stock_code': 'A', 'trade_date': '2024-01-01', 'close': 10.0},
            {'stock_code': 'A', 'trade_date': '2024-01-02', 'close': 10.5},
        ]

        codes = [f'{i:06d}.SH' for i in range(5)]
        result = _load_all_data_batched('online', '2024-01-01', codes, batch_size=2)

        self.assertGreater(len(result), 0)
        # 5 codes with batch_size=2 should produce 3 batches
        self.assertEqual(mock_query.call_count, 3)

    @patch('data_analyst.indicators.rps_calculator.execute_query')
    def test_empty_result(self, mock_query):
        """Should handle empty query results"""
        from data_analyst.indicators.rps_calculator import _load_all_data_batched

        mock_query.return_value = []
        result = _load_all_data_batched('online', '2024-01-01', ['A'], batch_size=1000)
        self.assertTrue(result.empty)


class TestRpsStorage(unittest.TestCase):

    @patch('data_analyst.indicators.rps_calculator.execute_query')
    def test_get_latest_date(self, mock_query):
        from data_analyst.indicators.rps_calculator import RPSStorage
        mock_query.return_value = [{'latest': '2024-08-16'}]
        storage = RPSStorage(env='online')
        self.assertEqual(storage.get_latest_date(), '2024-08-16')

    @patch('data_analyst.indicators.rps_calculator.execute_query')
    def test_get_latest_date_empty(self, mock_query):
        from data_analyst.indicators.rps_calculator import RPSStorage
        mock_query.return_value = [{'latest': None}]
        storage = RPSStorage(env='online')
        self.assertIsNone(storage.get_latest_date())


if __name__ == '__main__':
    unittest.main()
