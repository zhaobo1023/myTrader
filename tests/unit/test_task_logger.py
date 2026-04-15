# -*- coding: utf-8 -*-
"""
Unit tests for scheduler.task_logger.TaskLogger.

All DB calls are mocked -- no real database needed.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# Reset the module-level _table_ensured flag before each import
import scheduler.task_logger as tl_module


class TestTaskLoggerSuccess(unittest.TestCase):
    """TaskLogger should record running -> success on normal exit."""

    def setUp(self):
        tl_module._table_ensured = False

    @patch('scheduler.task_logger.execute_update', create=True)
    @patch('config.db.execute_update')
    def test_success_flow(self, mock_db_exec, mock_tl_exec):
        """Normal with-block records running then success."""
        # Both patches needed: _ensure_table and _upsert import execute_update
        # inside function body, so we mock config.db.execute_update
        mock_db_exec.return_value = 1

        with tl_module.TaskLogger('test_task', 'test_group',
                                   run_date='2026-04-16', env='local') as tl:
            tl.set_record_count(42)
            tl.set_detail({'sub': 'detail'})

        # Should have called execute_update at least 3 times:
        # 1) _ensure_table CREATE TABLE
        # 2) _upsert('running')
        # 3) _upsert('success')
        self.assertGreaterEqual(mock_db_exec.call_count, 3)

        # Verify the last call was 'success'
        last_call_args = mock_db_exec.call_args_list[-1]
        sql = last_call_args[0][0]
        params = last_call_args[0][1]
        self.assertIn('INSERT INTO trade_task_run_log', sql)
        self.assertEqual(params[0], '2026-04-16')  # run_date
        self.assertEqual(params[1], 'test_task')    # task_name
        self.assertEqual(params[2], 'test_group')   # task_group
        self.assertEqual(params[3], 'success')       # status
        self.assertEqual(params[7], 42)              # record_count
        self.assertIsNone(params[8])                 # error_msg (None on success)

    @patch('config.db.execute_update')
    def test_failure_flow(self, mock_db_exec):
        """Exception in with-block records 'failed' with error message."""
        tl_module._table_ensured = True  # skip DDL call
        mock_db_exec.return_value = 1

        with self.assertRaises(ValueError):
            with tl_module.TaskLogger('fail_task', 'factor',
                                       run_date='2026-04-16', env='local'):
                raise ValueError("something broke")

        # Last upsert should be 'failed'
        last_call_args = mock_db_exec.call_args_list[-1]
        params = last_call_args[0][1]
        self.assertEqual(params[3], 'failed')
        self.assertIn('ValueError', params[8])
        self.assertIn('something broke', params[8])

    @patch('config.db.execute_update')
    def test_exception_propagates(self, mock_db_exec):
        """TaskLogger must NOT swallow exceptions."""
        tl_module._table_ensured = True
        mock_db_exec.return_value = 1

        with self.assertRaises(RuntimeError):
            with tl_module.TaskLogger('x', 'y', env='local'):
                raise RuntimeError("must propagate")

    @patch('config.db.execute_update')
    def test_duration_ms_positive(self, mock_db_exec):
        """duration_ms should be a non-negative integer."""
        tl_module._table_ensured = True
        mock_db_exec.return_value = 1

        with tl_module.TaskLogger('dur_test', 'test', env='local'):
            pass

        # success upsert is the last call
        last_params = mock_db_exec.call_args_list[-1][0][1]
        duration_ms = last_params[6]
        self.assertIsNotNone(duration_ms)
        self.assertGreaterEqual(duration_ms, 0)

    @patch('config.db.execute_update')
    def test_default_run_date(self, mock_db_exec):
        """When run_date is not specified, defaults to today."""
        tl_module._table_ensured = True
        mock_db_exec.return_value = 1

        with tl_module.TaskLogger('date_test', 'test', env='local'):
            pass

        # running upsert (first call after table ensured)
        first_upsert_params = mock_db_exec.call_args_list[0][0][1]
        self.assertEqual(first_upsert_params[0], date.today().isoformat())

    @patch('config.db.execute_update')
    def test_upsert_db_failure_does_not_crash(self, mock_db_exec):
        """If _upsert fails, it should log a warning but not crash."""
        tl_module._table_ensured = True
        mock_db_exec.side_effect = Exception("DB connection lost")

        # Should NOT raise despite DB failure
        with tl_module.TaskLogger('resilient', 'test', env='local'):
            pass

    @patch('config.db.execute_update')
    def test_error_msg_truncation(self, mock_db_exec):
        """Error messages longer than 4000 chars get truncated."""
        tl_module._table_ensured = True
        mock_db_exec.return_value = 1

        with self.assertRaises(ValueError):
            with tl_module.TaskLogger('trunc', 'test', env='local'):
                raise ValueError("x" * 5000)

        last_params = mock_db_exec.call_args_list[-1][0][1]
        error_msg = last_params[8]
        self.assertLessEqual(len(error_msg), 4000)

    @patch('config.db.execute_update')
    def test_detail_json_serialization(self, mock_db_exec):
        """set_detail should serialize to JSON."""
        tl_module._table_ensured = True
        mock_db_exec.return_value = 1

        with tl_module.TaskLogger('json_test', 'test', env='local') as tl:
            tl.set_detail({'key': 'value', 'count': 123})

        import json
        last_params = mock_db_exec.call_args_list[-1][0][1]
        detail_json = last_params[9]
        self.assertIsNotNone(detail_json)
        parsed = json.loads(detail_json)
        self.assertEqual(parsed['key'], 'value')
        self.assertEqual(parsed['count'], 123)


class TestEnsureTable(unittest.TestCase):
    """Tests for the _ensure_table function."""

    def setUp(self):
        tl_module._table_ensured = False

    @patch('config.db.execute_update')
    def test_creates_table_once(self, mock_exec):
        """_ensure_table should only execute DDL once."""
        mock_exec.return_value = 1

        tl_module._ensure_table('local')
        tl_module._ensure_table('local')

        self.assertEqual(mock_exec.call_count, 1)
        self.assertTrue(tl_module._table_ensured)

    @patch('config.db.execute_update', side_effect=Exception("no DB"))
    def test_table_creation_failure_non_fatal(self, mock_exec):
        """If DDL fails, _table_ensured stays False but no exception raised."""
        tl_module._ensure_table('local')
        self.assertFalse(tl_module._table_ensured)


if __name__ == '__main__':
    unittest.main()
