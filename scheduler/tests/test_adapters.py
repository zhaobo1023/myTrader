# -*- coding: utf-8 -*-
"""Tests for scheduler.adapters module."""
import pytest

import scheduler.adapters as adapters


class TestAdaptersImport:
    def test_run_log_bias_exists(self):
        assert callable(adapters.run_log_bias)

    def test_run_technical_indicator_scan_exists(self):
        assert callable(adapters.run_technical_indicator_scan)

    def test_run_paper_trading_settle_exists(self):
        assert callable(adapters.run_paper_trading_settle)

    def test_run_industry_update_exists(self):
        assert callable(adapters.run_industry_update)


class TestAdaptersDryRun:
    def test_run_log_bias_dry_run(self):
        """dry_run=True should not raise."""
        adapters.run_log_bias(dry_run=True)

    def test_run_technical_indicator_scan_dry_run(self):
        adapters.run_technical_indicator_scan(dry_run=True)

    def test_run_paper_trading_settle_dry_run(self):
        adapters.run_paper_trading_settle(dry_run=True)

    def test_run_industry_update_dry_run(self):
        adapters.run_industry_update(dry_run=True)
