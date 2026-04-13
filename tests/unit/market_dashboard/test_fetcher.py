# -*- coding: utf-8 -*-
"""
Tests for market dashboard fetcher - date handling and helpers.
"""
import pytest


class TestNormalizeDate:
    """Test date format normalization."""

    def setup_method(self):
        from data_analyst.market_dashboard.fetcher import _normalize_date
        self._normalize = _normalize_date

    def test_already_normalized(self):
        assert self._normalize('2026-04-14') == '2026-04-14'

    def test_compact_format(self):
        assert self._normalize('20260414') == '2026-04-14'

    def test_slash_format(self):
        assert self._normalize('2026/04/14') == '2026-04-14'

    def test_with_spaces(self):
        assert self._normalize('  2026-04-14  ') == '2026-04-14'

    def test_compact_with_spaces(self):
        assert self._normalize(' 20260414 ') == '2026-04-14'


class TestToCompact:
    """Test conversion to YYYYMMDD format."""

    def setup_method(self):
        from data_analyst.market_dashboard.fetcher import _to_compact
        self._to_compact = _to_compact

    def test_from_dashed(self):
        assert self._to_compact('2026-04-14') == '20260414'

    def test_from_compact(self):
        assert self._to_compact('20260414') == '20260414'

    def test_from_slashed(self):
        assert self._to_compact('2026/04/14') == '20260414'
