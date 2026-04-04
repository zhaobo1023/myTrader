# -*- coding: utf-8 -*-
"""
YAML task loader with environment-specific merging.

Loads task definitions from tasks/*.yaml, merges with _base.yaml defaults,
and applies environment-specific overrides.
"""
import os
import glob
import logging
from copy import deepcopy
from typing import List, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Current environment: defaults to 'local'
ENV = os.getenv("MYTRADER_ENV", "local")


def load_tasks(tasks_dir: Optional[str] = None) -> List[Dict]:
    """
    Load all task definitions from YAML files.

    Args:
        tasks_dir: Path to the tasks directory. Defaults to <ROOT>/tasks/.

    Returns:
        List of task dicts, each with id, name, module, func, tags, etc.
    """
    if tasks_dir is None:
        tasks_dir = os.path.join(ROOT, "tasks")

    base = _load_base_defaults(tasks_dir)
    all_tasks = []

    # Load numbered YAML files in order (skip _base.yaml)
    pattern = os.path.join(tasks_dir, "[0-9]*.yaml")
    for filepath in sorted(glob.glob(pattern)):
        logger.debug("Loading tasks from %s", filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        raw_tasks = data.get("tasks", [])
        for task in raw_tasks:
            merged = _merge_task(base, task, ENV)
            errors = _validate_task(merged)
            if errors:
                for err in errors:
                    logger.error("Task validation error in %s: %s", filepath, err)
                continue
            all_tasks.append(merged)

    return all_tasks


def _load_base_defaults(tasks_dir: str) -> Dict:
    """
    Load _base.yaml and merge defaults + environment overrides.

    Returns a base dict with merged defaults and env-specific settings.
    """
    base_path = os.path.join(tasks_dir, "_base.yaml")
    if not os.path.exists(base_path):
        return {"defaults": {}, "env_overrides": {}}

    with open(base_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    defaults = data.get("defaults", {})
    environments = data.get("environments", {})

    # Merge environment-specific overrides on top of defaults
    env_settings = environments.get(ENV, {})
    merged_defaults = deepcopy(defaults)
    _deep_merge(merged_defaults, env_settings)

    return {
        "defaults": merged_defaults,
        "env_overrides": environments,
    }


def _merge_task(base: Dict, task: Dict, env: str) -> Dict:
    """
    Three-layer merge: base defaults -> task definition -> environment overrides.

    The task definition takes precedence over base defaults.
    Environment-specific task settings (task.env.<env>) take highest precedence.
    """
    result = deepcopy(base["defaults"])

    # Layer 1: task-level fields override defaults
    for key, value in task.items():
        if key == "env":
            continue  # env overrides handled separately
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)

    # Layer 2: environment-specific task overrides
    task_env = task.get("env", {})
    if isinstance(task_env, dict):
        env_override = task_env.get(env, {})
        for key, value in env_override.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                _deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)

    # Ensure essential list fields exist
    result.setdefault("depends_on", [])
    result.setdefault("tags", [])
    result.setdefault("params", {})

    return result


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override into base (mutates base)."""
    for key, value in override.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _validate_task(task: Dict) -> List[str]:
    """Validate required fields. Returns list of error messages."""
    errors = []
    if not task.get("id"):
        errors.append("Missing required field: id")
    if not task.get("module"):
        errors.append(f"Task '{task.get('id', '?')}': missing required field: module")
    if not task.get("func"):
        errors.append(f"Task '{task.get('id', '?')}': missing required field: func")
    return errors
