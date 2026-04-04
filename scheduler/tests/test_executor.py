# -*- coding: utf-8 -*-
"""Tests for scheduler.executor module."""
import pytest
from unittest.mock import patch, MagicMock
from scheduler.executor import execute_task


def _make_task(tid, deps=None, enabled=True, schedule="", module="scheduler.adapters", func="run_log_bias", params=None):
    return {
        "id": tid,
        "name": f"Task {tid}",
        "module": module,
        "func": func,
        "depends_on": deps or [],
        "enabled": enabled,
        "schedule": schedule,
        "params": params or {},
    }


class TestExecuteTask:
    def test_skip_disabled(self):
        task = _make_task("t1", enabled=False)
        result = execute_task(task, {}, dry_run=True)
        assert result == "skipped"

    def test_skip_upstream_failed(self):
        task = _make_task("t2", deps=["t1"])
        completed = {"t1": "failed"}
        result = execute_task(task, completed, dry_run=True)
        assert result == "skipped"

    def test_skip_upstream_not_completed(self):
        task = _make_task("t2", deps=["t1"])
        completed = {}
        result = execute_task(task, completed, dry_run=True)
        assert result == "skipped"

    def test_dry_run_success(self):
        task = _make_task("t1")
        result = execute_task(task, {}, dry_run=True)
        assert result == "success"

    def test_execute_success_with_mock(self):
        """Mock the actual function call to test execution path."""
        task = _make_task("t1", module="scheduler.tests.test_executor", func="_mock_success_fn", params={"x": 1})

        result = execute_task(task, {}, dry_run=False)
        assert result == "success"

    def test_execute_failure_with_mock(self):
        """Test that a failing function returns 'failed'."""
        task = _make_task("t1", module="scheduler.tests.test_executor", func="_mock_failure_fn")

        result = execute_task(task, {}, dry_run=False)
        assert result == "failed"

    def test_skip_manual_in_prod(self):
        task = _make_task("t1", schedule="manual")
        result = execute_task(task, {}, dry_run=False, env="prod")
        assert result == "skipped"

    def test_manual_allowed_with_dry_run(self):
        """Manual tasks should run in dry_run even in prod."""
        task = _make_task("t1", schedule="manual")
        result = execute_task(task, {}, dry_run=True, env="prod")
        assert result == "success"


def _mock_success_fn(x=0):
    """Mock function for testing successful execution."""
    return x + 1


def _mock_failure_fn():
    """Mock function for testing failed execution."""
    raise RuntimeError("Simulated failure")
