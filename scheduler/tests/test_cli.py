# -*- coding: utf-8 -*-
"""Tests for CLI skeleton."""
import subprocess
import sys


def test_list_returns_zero():
    result = subprocess.run(
        [sys.executable, "-m", "scheduler", "list"],
        capture_output=True,
        text=True,
        cwd=_project_root(),
    )
    assert result.returncode == 0


def test_unknown_command_returns_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "scheduler", "nonexistent"],
        capture_output=True,
        text=True,
        cwd=_project_root(),
    )
    assert result.returncode != 0


def _project_root():
    import os
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
