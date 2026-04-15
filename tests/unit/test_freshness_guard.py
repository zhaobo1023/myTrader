# -*- coding: utf-8 -*-
"""
Unit tests for scheduler.freshness_guard.

All DB calls and trigger functions are mocked.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from scheduler.freshness_guard import (
    check_freshness, ensure_factors_fresh, _try_trigger,
    STRATEGY_REQUIREMENTS, FACTOR_TRIGGERS,
)


class TestCheckFreshness(unittest.TestCase):
    """Tests for check_freshness()."""

    @patch('config.db.execute_query')
    def test_all_fresh(self, mock_query):
        """Returns (True, []) when all tables are within max_lag."""
        mock_query.return_value = [{'d': date.today()}]

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        ])
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    @patch('config.db.execute_query')
    def test_stale_data(self, mock_query):
        """Returns (False, [...]) when data is too old."""
        mock_query.return_value = [{'d': date.today() - timedelta(days=5)}]

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        ])
        self.assertFalse(ok)
        self.assertEqual(len(issues), 1)
        self.assertIn('trade_stock_daily', issues[0])
        self.assertIn('lag=5d', issues[0])

    @patch('config.db.execute_query')
    def test_no_data(self, mock_query):
        """Returns (False, [...]) when table has no rows."""
        mock_query.return_value = [{'d': None}]

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        ])
        self.assertFalse(ok)
        self.assertIn('no data', issues[0])

    @patch('config.db.execute_query')
    def test_empty_result(self, mock_query):
        """Returns (False, [...]) when query returns empty."""
        mock_query.return_value = []

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        ])
        self.assertFalse(ok)
        self.assertIn('no data', issues[0])

    @patch('config.db.execute_query')
    def test_query_exception(self, mock_query):
        """Returns (False, [...]) when query throws."""
        mock_query.side_effect = Exception("connection timeout")

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        ])
        self.assertFalse(ok)
        self.assertIn('query failed', issues[0])

    @patch('config.db.execute_query')
    def test_boundary_exactly_max_lag(self, mock_query):
        """Data exactly max_lag days old should be considered fresh."""
        mock_query.return_value = [{'d': date.today() - timedelta(days=2)}]

        ok, issues = check_freshness([
            {'table': 'trade_stock_rps', 'date_col': 'trade_date', 'max_lag': 2},
        ])
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    @patch('config.db.execute_query')
    def test_boundary_one_over_max_lag(self, mock_query):
        """Data max_lag+1 days old should be stale."""
        mock_query.return_value = [{'d': date.today() - timedelta(days=3)}]

        ok, issues = check_freshness([
            {'table': 'trade_stock_rps', 'date_col': 'trade_date', 'max_lag': 2},
        ])
        self.assertFalse(ok)

    @patch('config.db.execute_query')
    def test_multiple_requirements_partial_stale(self, mock_query):
        """One fresh + one stale -> overall False, 1 issue."""
        def side_effect(sql, env=None):
            if 'trade_stock_daily' in sql:
                return [{'d': date.today()}]
            else:
                return [{'d': date.today() - timedelta(days=10)}]

        mock_query.side_effect = side_effect

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
            {'table': 'trade_stock_rps', 'date_col': 'trade_date', 'max_lag': 2},
        ])
        self.assertFalse(ok)
        self.assertEqual(len(issues), 1)
        self.assertIn('trade_stock_rps', issues[0])

    @patch('config.db.execute_query')
    def test_string_date_handling(self, mock_query):
        """Should handle string dates returned from DB."""
        mock_query.return_value = [{'d': date.today().isoformat()}]

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        ])
        self.assertTrue(ok)

    @patch('config.db.execute_query')
    def test_datetime_date_handling(self, mock_query):
        """Should handle datetime objects (via .date())."""
        from datetime import datetime
        mock_query.return_value = [{'d': datetime.now()}]

        ok, issues = check_freshness([
            {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        ])
        self.assertTrue(ok)

    @patch('config.db.execute_query')
    def test_env_passed_through(self, mock_query):
        """env parameter is forwarded to execute_query."""
        mock_query.return_value = [{'d': date.today()}]

        check_freshness([
            {'table': 't', 'date_col': 'd', 'max_lag': 1},
        ], env='local')

        mock_query.assert_called_once()
        _, kwargs = mock_query.call_args
        self.assertEqual(kwargs['env'], 'local')


class TestEnsureFactorsFresh(unittest.TestCase):
    """Tests for ensure_factors_fresh()."""

    def test_unknown_strategy_raises_valueerror(self):
        """Unknown strategy name should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            ensure_factors_fresh('nonexistent_strategy')
        self.assertIn('nonexistent_strategy', str(ctx.exception))

    @patch('scheduler.freshness_guard.check_freshness')
    def test_all_fresh_returns_immediately(self, mock_check):
        """When data is fresh, no trigger is called."""
        mock_check.return_value = (True, [])

        # Should not raise
        ensure_factors_fresh('log_bias', env='local')
        mock_check.assert_called_once()

    @patch('scheduler.freshness_guard._try_trigger')
    @patch('scheduler.freshness_guard.check_freshness')
    def test_stale_no_trigger_raises(self, mock_check, mock_trigger):
        """Stale data with no trigger available -> RuntimeError."""
        mock_check.return_value = (False, ['trade_stock_daily: lag=5d > max_lag=1d'])
        mock_trigger.return_value = False

        with self.assertRaises(RuntimeError) as ctx:
            ensure_factors_fresh('log_bias', env='local')
        self.assertIn('blocked', str(ctx.exception))

    @patch('scheduler.freshness_guard._try_trigger')
    @patch('scheduler.freshness_guard.check_freshness')
    def test_stale_trigger_then_fresh(self, mock_check, mock_trigger):
        """Stale -> trigger -> re-check fresh -> success."""
        # First check: stale. Second check: fresh.
        mock_check.side_effect = [
            (False, ['trade_stock_basic_factor: lag=5d > max_lag=2d']),
            (True, []),
        ]
        mock_trigger.return_value = True

        # Should not raise
        ensure_factors_fresh('xgboost', env='local')
        mock_trigger.assert_called_once()
        self.assertEqual(mock_check.call_count, 2)

    @patch('scheduler.freshness_guard._try_trigger')
    @patch('scheduler.freshness_guard.check_freshness')
    def test_stale_trigger_still_stale_raises(self, mock_check, mock_trigger):
        """Stale -> trigger -> re-check still stale -> RuntimeError."""
        mock_check.side_effect = [
            (False, ['trade_stock_basic_factor: lag=5d > max_lag=2d']),
            (False, ['trade_stock_basic_factor: lag=5d > max_lag=2d']),
        ]
        mock_trigger.return_value = True

        with self.assertRaises(RuntimeError) as ctx:
            ensure_factors_fresh('xgboost', env='local')
        self.assertIn('still blocked', str(ctx.exception))


class TestTryTrigger(unittest.TestCase):
    """Tests for _try_trigger()."""

    def test_no_trigger_defined(self):
        """Table with no trigger returns False."""
        result = _try_trigger('trade_stock_daily', env='local')
        self.assertFalse(result)

    @patch('importlib.import_module')
    def test_trigger_success(self, mock_import):
        """Trigger invoked successfully returns True."""
        mock_mod = MagicMock()
        mock_import.return_value = mock_mod

        result = _try_trigger('trade_stock_basic_factor', env='local')

        self.assertTrue(result)
        mock_import.assert_called_once_with('data_analyst.factors.basic_factor_calculator')
        mock_mod.calculate_and_save_factors.assert_called_once()

    @patch('importlib.import_module', side_effect=ImportError("no module"))
    def test_trigger_import_failure(self, mock_import):
        """Import failure returns False (does not raise)."""
        result = _try_trigger('trade_stock_basic_factor', env='local')
        self.assertFalse(result)


class TestStrategyRequirements(unittest.TestCase):
    """Verify STRATEGY_REQUIREMENTS dict structure."""

    def test_all_strategies_have_requirements(self):
        """Each strategy should have at least one requirement."""
        for name, reqs in STRATEGY_REQUIREMENTS.items():
            self.assertIsInstance(reqs, list, f"{name} should map to a list")
            self.assertGreater(len(reqs), 0, f"{name} should have >= 1 requirement")

    def test_requirement_keys(self):
        """Each requirement dict should have table, date_col, max_lag."""
        for name, reqs in STRATEGY_REQUIREMENTS.items():
            for req in reqs:
                self.assertIn('table', req, f"{name} requirement missing 'table'")
                self.assertIn('date_col', req, f"{name} requirement missing 'date_col'")
                self.assertIn('max_lag', req, f"{name} requirement missing 'max_lag'")
                self.assertIsInstance(req['max_lag'], int)
                self.assertGreater(req['max_lag'], 0)

    def test_factor_triggers_format(self):
        """Each trigger path should be module.function format."""
        for table, path in FACTOR_TRIGGERS.items():
            parts = path.rsplit('.', 1)
            self.assertEqual(len(parts), 2, f"{table} trigger path should have module.func: {path}")


if __name__ == '__main__':
    unittest.main()
