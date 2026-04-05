# -*- coding: utf-8 -*-
"""Tests for scheduler.dag module."""
import pytest

from scheduler.dag import (
    resolve_batches,
    validate_dependencies,
    filter_by_tag,
    filter_by_tags,
    filter_by_id,
    build_subgraph,
    run_dag,
)


def _make_task(tid, deps=None, tags=None):
    return {"id": tid, "module": f"mod_{tid}", "func": f"fn_{tid}",
            "depends_on": deps or [], "tags": tags or []}


class TestResolveBatches:
    def test_no_deps_single_batch(self):
        tasks = [_make_task("a"), _make_task("b"), _make_task("c")]
        batches = resolve_batches(tasks)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_linear_deps_multi_batch(self):
        tasks = [
            _make_task("a", []),
            _make_task("b", ["a"]),
            _make_task("c", ["b"]),
        ]
        batches = resolve_batches(tasks)
        assert len(batches) == 3
        assert batches[0][0]["id"] == "a"
        assert batches[1][0]["id"] == "b"
        assert batches[2][0]["id"] == "c"

    def test_diamond_dependency(self):
        """A -> B, A -> C, B -> D, C -> D  => 3 batches."""
        tasks = [
            _make_task("a", []),
            _make_task("b", ["a"]),
            _make_task("c", ["a"]),
            _make_task("d", ["b", "c"]),
        ]
        batches = resolve_batches(tasks)
        assert len(batches) == 3
        assert {t["id"] for t in batches[0]} == {"a"}
        assert {t["id"] for t in batches[1]} == {"b", "c"}
        assert {t["id"] for t in batches[2]} == {"d"}

    def test_missing_deps_ignored(self):
        """Dependencies not in the task set are silently ignored."""
        tasks = [
            _make_task("a", ["nonexistent"]),
        ]
        batches = resolve_batches(tasks)
        assert len(batches) == 1
        assert batches[0][0]["id"] == "a"


class TestValidateDependencies:
    def test_valid_no_errors(self):
        tasks = [
            _make_task("a", []),
            _make_task("b", ["a"]),
        ]
        errors = validate_dependencies(tasks)
        assert errors == []

    def test_missing_dependency(self):
        tasks = [_make_task("a", ["missing"])]
        errors = validate_dependencies(tasks)
        assert len(errors) == 1
        assert "missing" in errors[0]

    def test_circular_dependency(self):
        tasks = [
            _make_task("a", ["b"]),
            _make_task("b", ["a"]),
        ]
        errors = validate_dependencies(tasks)
        assert any("ircular" in e for e in errors)


class TestFiltering:
    def test_filter_by_tag(self):
        tasks = [
            _make_task("a", tags=["daily"]),
            _make_task("b", tags=["manual"]),
        ]
        result = filter_by_tag(tasks, "daily")
        assert len(result) == 1
        assert result[0]["id"] == "a"

    def test_filter_by_multiple_tags(self):
        tasks = [
            _make_task("a", tags=["daily", "factor"]),
            _make_task("b", tags=["daily"]),
            _make_task("c", tags=["manual", "factor"]),
        ]
        result = filter_by_tags(tasks, ["daily", "factor"])
        assert len(result) == 1
        assert result[0]["id"] == "a"

    def test_filter_by_id(self):
        tasks = [_make_task("a"), _make_task("b")]
        result = filter_by_id(tasks, "b")
        assert len(result) == 1
        assert result[0]["id"] == "b"


class TestBuildSubgraph:
    def test_single_target_no_deps(self):
        tasks = [_make_task("a"), _make_task("b")]
        sub = build_subgraph(tasks, ["a"])
        ids = [t["id"] for t in sub]
        assert ids == ["a"]

    def test_target_with_deps(self):
        tasks = [
            _make_task("a", []),
            _make_task("b", ["a"]),
            _make_task("c", ["b"]),
        ]
        sub = build_subgraph(tasks, ["c"])
        ids = [t["id"] for t in sub]
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids

    def test_missing_target_ignored(self):
        tasks = [_make_task("a")]
        sub = build_subgraph(tasks, ["nonexistent"])
        assert sub == []


class TestRunDag:
    def test_dry_run(self):
        tasks = [_make_task("a"), _make_task("b")]
        completed = run_dag(tasks, lambda t, c: "success", dry_run=True)
        assert completed == {"a": "success", "b": "success"}

    def test_execute_in_order(self):
        order = []
        tasks = [
            _make_task("a", []),
            _make_task("b", ["a"]),
        ]

        def executor(task, completed):
            order.append(task["id"])
            return "success"

        completed = run_dag(tasks, executor)
        assert order == ["a", "b"]
        assert completed == {"a": "success", "b": "success"}

    def test_upstream_failure_skips(self):
        """When task 'a' fails, task 'b' (which depends on 'a') is still executed
        by default. The executor is responsible for checking upstream status."""
        tasks = [
            _make_task("a", []),
            _make_task("b", ["a"]),
        ]

        def executor(task, completed):
            if task["id"] == "a":
                return "failed"
            return "success"

        completed = run_dag(tasks, executor)
        assert completed["a"] == "failed"
        # b still runs because run_dag doesn't auto-skip; executor decides
        assert completed["b"] == "success"
