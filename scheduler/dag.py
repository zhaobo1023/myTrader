# -*- coding: utf-8 -*-
"""
DAG dependency resolver using graphlib.TopologicalSorter.

Provides topological batching, dependency validation, tag filtering,
and subgraph extraction.
"""
import logging
from collections import deque
from graphlib import TopologicalSorter
from typing import List, Dict, Set, Optional

logger = logging.getLogger(__name__)


def resolve_batches(tasks: List[Dict]) -> List[List[Dict]]:
    """
    Resolve task dependencies into execution batches.

    Tasks with no unmet dependencies are in the same batch.
    Within a batch, tasks can be executed in parallel.

    Args:
        tasks: List of task dicts with 'id' and 'depends_on' fields.

    Returns:
        List of batches, where each batch is a list of task dicts.
    """
    task_map = {t["id"]: t for t in tasks}
    all_ids = set(task_map.keys())

    # Build dependency graph: only include dependencies that exist in the task set
    graph = {}
    for t in tasks:
        tid = t["id"]
        deps = [d for d in t.get("depends_on", []) if d in all_ids]
        graph[tid] = deps

    sorter = TopologicalSorter(graph)
    sorter.prepare()  # Required on Python 3.9
    batches = []
    ready = set(sorter.get_ready())

    while ready:
        batch = [task_map[tid] for tid in sorted(ready)]
        batches.append(batch)
        sorter.done(*ready)
        ready = set(sorter.get_ready())

    return batches


def validate_dependencies(tasks: List[Dict]) -> List[str]:
    """
    Validate task dependencies.

    Returns:
        List of warning/error messages about missing or circular dependencies.
    """
    errors = []
    task_ids = {t["id"] for t in tasks}

    # Check for missing dependencies
    for t in tasks:
        for dep in t.get("depends_on", []):
            if dep not in task_ids:
                errors.append(f"Task '{t['id']}' depends on '{dep}' which does not exist")

    # Check for circular dependencies via TopologicalSorter
    graph = {t["id"]: t.get("depends_on", []) for t in tasks}
    try:
        TopologicalSorter(graph).prepare()
    except ValueError as e:
        errors.append(f"Circular dependency detected: {e}")

    return errors


def filter_by_tag(tasks: List[Dict], tag: str) -> List[Dict]:
    """Filter tasks by a single tag."""
    return [t for t in tasks if tag in t.get("tags", [])]


def filter_by_tags(tasks: List[Dict], tags: List[str]) -> List[Dict]:
    """Filter tasks that have ALL specified tags."""
    result = tasks
    for tag in tags:
        result = [t for t in result if tag in t.get("tags", [])]
    return result


def filter_by_id(tasks: List[Dict], task_id: str) -> List[Dict]:
    """Filter to a single task by ID."""
    return [t for t in tasks if t["id"] == task_id]


def build_subgraph(tasks: List[Dict], target_ids: List[str]) -> List[Dict]:
    """
    Build a subgraph containing the target tasks and all their transitive dependencies.

    Args:
        tasks: Full list of task dicts.
        target_ids: IDs of tasks to include (with their dependencies).

    Returns:
        List of task dicts forming the subgraph.
    """
    task_map = {t["id"]: t for t in tasks}
    target_set = set(target_ids)
    visited = set()
    result = []

    def _collect(tid):
        if tid in visited:
            return
        if tid not in task_map:
            return
        visited.add(tid)
        task = task_map[tid]
        # Collect dependencies first
        for dep in task.get("depends_on", []):
            _collect(dep)
        result.append(task)

    for tid in target_ids:
        _collect(tid)

    return result


def run_dag(
    tasks: List[Dict],
    executor_fn,
    max_workers: int = 4,
    dry_run: bool = False,
) -> Dict[str, str]:
    """
    Execute tasks in dependency order using batches.

    Args:
        tasks: List of task dicts to execute.
        executor_fn: Callable(task, completed_dict) -> str (returns 'success'/'failed'/'skipped').
        max_workers: Max parallel workers per batch (reserved for future use).
        dry_run: If True, only print what would be executed.

    Returns:
        Dict mapping task_id -> status ('success'/'failed'/'skipped').
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    batches = resolve_batches(tasks)
    completed = {}  # task_id -> status

    for i, batch in enumerate(batches):
        logger.info("Batch %d: %s", i + 1, [t["id"] for t in batch])

        if dry_run:
            for t in batch:
                logger.info("[DRY-RUN] Would execute: %s", t["id"])
                completed[t["id"]] = "success"
            continue

        # Execute batch sequentially (parallel is reserved for future)
        for t in batch:
            status = executor_fn(t, completed)
            completed[t["id"]] = status
            if status == "failed" and not t.get("continue_on_failure", False):
                logger.warning("Task %s failed, skipping dependents", t["id"])

    return completed
