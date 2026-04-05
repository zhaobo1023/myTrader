# -*- coding: utf-8 -*-
"""Tests for scheduler.readiness module."""
from datetime import datetime
from scheduler.readiness import expected_trade_date


class TestExpectedTradeDate:
    def test_format_is_yyyy_mm_dd(self):
        result = expected_trade_date()
        # Should be YYYY-MM-DD format
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2
        assert len(parts[2]) == 2

    def test_returns_string(self):
        assert isinstance(expected_trade_date(), str)

    def test_dry_run_returns_true(self):
        """wait_for_daily_data with dry_run=True should return True."""
        from scheduler.readiness import wait_for_daily_data
        result = wait_for_daily_data(dry_run=True)
        assert result is True
