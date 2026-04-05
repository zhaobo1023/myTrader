# -*- coding: utf-8 -*-
"""Tests for scheduler.loader module."""
import os
import tempfile

import pytest

from scheduler.loader import (
    _load_base_defaults,
    _merge_task,
    _validate_task,
    load_tasks,
)


class TestLoadBaseDefaults:
    def test_loads_base_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = os.path.join(tmpdir, "_base.yaml")
            with open(base_path, "w") as f:
                f.write("defaults:\n  timeout_seconds: 600\n  enabled: true\n"
                        "environments:\n  local:\n    dry_run: true\n")

            base = _load_base_defaults(tmpdir)
            assert base["defaults"]["timeout_seconds"] == 600
            assert base["defaults"]["enabled"] is True
            assert base["defaults"]["dry_run"] is True  # env override applied

    def test_missing_base_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _load_base_defaults(tmpdir)
            assert base["defaults"] == {}
            assert base["env_overrides"] == {}


class TestMergeTask:
    def test_base_defaults_applied(self):
        base = {"defaults": {"timeout_seconds": 300, "enabled": True, "retry": {"max_attempts": 3}}}
        task = {"id": "t1", "module": "m1", "func": "f1"}
        result = _merge_task(base, task, "local")
        assert result["timeout_seconds"] == 300
        assert result["enabled"] is True
        assert result["retry"]["max_attempts"] == 3

    def test_task_overrides_base(self):
        base = {"defaults": {"timeout_seconds": 300, "enabled": True}}
        task = {"id": "t1", "module": "m1", "func": "f1", "timeout_seconds": 600}
        result = _merge_task(base, task, "local")
        assert result["timeout_seconds"] == 600

    def test_env_override_highest_priority(self):
        base = {"defaults": {"enabled": True}}
        task = {"id": "t1", "module": "m1", "func": "f1", "enabled": False,
                "env": {"prod": {"enabled": True}}}
        result = _merge_task(base, task, "prod")
        assert result["enabled"] is True

    def test_list_fields_default_empty(self):
        base = {"defaults": {}}
        task = {"id": "t1", "module": "m1", "func": "f1"}
        result = _merge_task(base, task, "local")
        assert result["depends_on"] == []
        assert result["tags"] == []
        assert result["params"] == {}

    def test_deep_merge_retry(self):
        base = {"defaults": {"retry": {"max_attempts": 2, "delay_seconds": 30}}}
        task = {"id": "t1", "module": "m1", "func": "f1",
                "retry": {"max_attempts": 5}}
        result = _merge_task(base, task, "local")
        assert result["retry"]["max_attempts"] == 5
        assert result["retry"]["delay_seconds"] == 30  # preserved from base


class TestValidateTask:
    def test_valid_task(self):
        errors = _validate_task({"id": "t1", "module": "m", "func": "f"})
        assert errors == []

    def test_missing_id(self):
        errors = _validate_task({"module": "m", "func": "f"})
        assert any("id" in e for e in errors)

    def test_missing_module(self):
        errors = _validate_task({"id": "t1", "func": "f"})
        assert any("module" in e for e in errors)

    def test_missing_func(self):
        errors = _validate_task({"id": "t1", "module": "m"})
        assert any("func" in e for e in errors)


class TestLoadTasks:
    def test_load_from_directory(self):
        """Test loading tasks from the actual tasks/ directory."""
        tasks = load_tasks()
        assert len(tasks) >= 2  # at least the 2 macro tasks
        ids = [t["id"] for t in tasks]
        assert "fetch_macro_data" in ids
        assert "calc_macro_factors" in ids

    def test_tasks_have_required_fields(self):
        tasks = load_tasks()
        for t in tasks:
            assert t["id"], f"Task missing id"
            assert t["module"], f"Task missing module"
            assert t["func"], f"Task missing func"

    def test_macro_task_dependency(self):
        tasks = load_tasks()
        calc_macro = next(t for t in tasks if t["id"] == "calc_macro_factors")
        assert "fetch_macro_data" in calc_macro["depends_on"]
