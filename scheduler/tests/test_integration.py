# -*- coding: utf-8 -*-
"""
Integration tests for the scheduler system.

Tests that require no database connection.
"""
import pytest

from scheduler.loader import load_tasks
from scheduler.dag import resolve_batches, validate_dependencies


class TestYAMLLoading:
    def test_all_yaml_files_load_without_error(self):
        """All YAML task files should load without exceptions."""
        tasks = load_tasks()
        assert isinstance(tasks, list)

    def test_at_least_expected_tasks(self):
        """Should have at least the macro + gate + factor tasks."""
        tasks = load_tasks()
        ids = {t["id"] for t in tasks}
        assert len(ids) >= 15
        # Key tasks that must exist
        assert "fetch_macro_data" in ids
        assert "calc_macro_factors" in ids
        assert "_gate_daily_price" in ids
        assert "calc_basic_factor" in ids
        assert "calc_rps" in ids
        assert "calc_svd_monitor" in ids

    def test_all_tasks_have_required_fields(self):
        tasks = load_tasks()
        for t in tasks:
            assert t["id"], f"Task missing id"
            assert t["module"], f"Task missing module"
            assert t["func"], f"Task missing func"
            assert isinstance(t.get("depends_on", []), list)


class TestDAGValidation:
    def test_no_dependency_cycles(self):
        """Full task set should have no circular dependencies."""
        tasks = load_tasks()
        errors = validate_dependencies(tasks)
        cycle_errors = [e for e in errors if "ircular" in e]
        assert cycle_errors == [], f"Circular dependencies found: {cycle_errors}"

    def test_resolve_batches_succeeds(self):
        """All tasks should resolve into valid batches."""
        tasks = load_tasks()
        batches = resolve_batches(tasks)
        assert len(batches) >= 2  # At least gate batch + dependent batch

    def test_gate_in_first_batch(self):
        """_gate_daily_price should be in the first batch."""
        tasks = load_tasks()
        batches = resolve_batches(tasks)
        first_batch_ids = {t["id"] for t in batches[0]}
        # Tasks with no deps should be in first batch
        zero_dep_tasks = [t for t in tasks if not t.get("depends_on", [])]
        for t in zero_dep_tasks:
            assert t["id"] in first_batch_ids, \
                f"{t['id']} has no deps but not in first batch"


class TestTagFiltering:
    def test_daily_tag_exists(self):
        tasks = load_tasks()
        daily = [t for t in tasks if "daily" in t.get("tags", [])]
        assert len(daily) >= 10

    def test_manual_tag_exists(self):
        tasks = load_tasks()
        manual = [t for t in tasks if "manual" in t.get("tags", [])]
        assert len(manual) >= 3

    def test_factor_tag_exists(self):
        tasks = load_tasks()
        factor = [t for t in tasks if "factor" in t.get("tags", [])]
        assert len(factor) >= 4


class TestAdapterFunctions:
    def test_all_adapter_functions_exist(self):
        """Verify adapter module exposes the expected functions."""
        import scheduler.adapters as adapters
        assert callable(adapters.run_log_bias)
        assert callable(adapters.run_technical_indicator_scan)
        assert callable(adapters.run_paper_trading_settle)
        assert callable(adapters.run_industry_update)

    def test_all_adapters_dry_run(self):
        """All adapter functions should accept dry_run=True without error."""
        import scheduler.adapters as adapters
        adapters.run_log_bias(dry_run=True)
        adapters.run_technical_indicator_scan(dry_run=True)
        adapters.run_paper_trading_settle(dry_run=True)
        adapters.run_industry_update(dry_run=True)


class TestDryRunAllDaily:
    def test_all_daily_tasks_dry_run(self):
        """All daily-tagged tasks should succeed in dry-run mode."""
        from scheduler.executor import execute_task
        from scheduler.dag import filter_by_tag, run_dag

        tasks = load_tasks()
        daily_tasks = filter_by_tag(tasks, "daily")

        completed = run_dag(
            daily_tasks,
            executor_fn=lambda t, c: execute_task(t, c, dry_run=True),
            dry_run=True,
        )

        # All should succeed or be skipped (none should fail)
        for tid, status in completed.items():
            assert status in ("success", "skipped"), \
                f"Task {tid} got status {status} in dry-run"


class TestCLIEndToEnd:
    def test_list_command(self, capsys):
        """python -m scheduler list should produce output."""
        import subprocess
        import sys
        import os
        result = subprocess.run(
            [sys.executable, "-m", "scheduler", "list"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        assert result.returncode == 0
        assert "fetch_macro_data" in result.stdout

    def test_list_tag_filter(self, capsys):
        """python -m scheduler list --tag manual should filter correctly."""
        import subprocess
        import sys
        import os
        result = subprocess.run(
            [sys.executable, "-m", "scheduler", "list", "--tag", "manual"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        assert result.returncode == 0
        assert "update_industry_classify" in result.stdout
        assert "fetch_macro_data" not in result.stdout

    def test_run_all_dry_run(self):
        """python -m scheduler run all --dry-run should succeed."""
        import subprocess
        import sys
        import os
        result = subprocess.run(
            [sys.executable, "-m", "scheduler", "run", "all", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        assert result.returncode == 0

    def test_run_single_dry_run(self):
        """python -m scheduler run fetch_macro_data --dry-run should succeed."""
        import subprocess
        import sys
        import os
        result = subprocess.run(
            [sys.executable, "-m", "scheduler", "run", "fetch_macro_data", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        assert result.returncode == 0
