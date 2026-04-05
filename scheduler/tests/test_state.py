# -*- coding: utf-8 -*-
"""Tests for scheduler.state module."""
import pytest
from scheduler.state import TaskRun, CREATE_TABLE_SQL


class TestTaskRun:
    def test_create_with_defaults(self):
        run = TaskRun(task_id="test_task")
        assert run.task_id == "test_task"
        assert run.status == "pending"
        assert run.started_at is not None
        assert run.finished_at is None

    def test_create_with_all_fields(self):
        run = TaskRun(
            task_id="t1",
            env="online",
            status="success",
            duration_s=5.0,
            error_msg=None,
            retry_count=2,
            triggered_by="scheduler",
        )
        assert run.env == "online"
        assert run.status == "success"
        assert run.retry_count == 2

    def test_started_at_auto_set(self):
        run = TaskRun(task_id="t2")
        assert run.started_at is not None
        assert len(run.started_at) == 19  # YYYY-MM-DD HH:MM:SS


class TestDDL:
    def test_create_table_sql_valid(self):
        """DDL should contain essential columns and be valid SQL syntax."""
        assert "CREATE TABLE IF NOT EXISTS task_runs" in CREATE_TABLE_SQL
        assert "task_id" in CREATE_TABLE_SQL
        assert "status" in CREATE_TABLE_SQL
        assert "started_at" in CREATE_TABLE_SQL
        assert "finished_at" in CREATE_TABLE_SQL
        assert "duration_s" in CREATE_TABLE_SQL
        assert "error_msg" in CREATE_TABLE_SQL

    def test_ddl_uses_pymysql_placeholders(self):
        """DDL should not contain SQLAlchemy-style placeholders."""
        assert ":param" not in CREATE_TABLE_SQL.lower()
