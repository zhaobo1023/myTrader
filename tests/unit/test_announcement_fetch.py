# -*- coding: utf-8 -*-
"""
Unit tests for announcement fetch adapter and enhanced _news_score.

Tests are pure-Python: no DB, no network, no LLM.
We mock external dependencies and test logic in isolation.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Tests for _news_score and _neg_ratio_risk
# ---------------------------------------------------------------------------

class TestNegRatioRisk:
    """Test the legacy neg_ratio scoring function."""

    def setup_method(self):
        from data_analyst.risk_assessment.assessors.stock import _neg_ratio_risk
        self.fn = _neg_ratio_risk

    def test_none_returns_default(self):
        assert self.fn(None) == 40.0

    def test_high_negative(self):
        assert self.fn(0.6) == 80.0

    def test_medium_negative(self):
        assert self.fn(0.3) == 60.0

    def test_low_negative(self):
        assert self.fn(0.15) == 40.0

    def test_very_low_negative(self):
        assert self.fn(0.05) == 20.0

    def test_zero_negative(self):
        assert self.fn(0.0) == 20.0

    def test_boundary_0_5(self):
        # exactly 0.5 -> >=0.3 branch
        assert self.fn(0.5) == 60.0

    def test_boundary_0_3(self):
        # exactly 0.3 -> >=0.3 branch
        assert self.fn(0.3) == 60.0

    def test_boundary_0_1(self):
        # exactly 0.1 -> >=0.1 branch
        assert self.fn(0.1) == 40.0


class TestNewsScore:
    """Test the enhanced _news_score with LLM fusion."""

    def setup_method(self):
        from data_analyst.risk_assessment.assessors.stock import _news_score
        self.fn = _news_score

    def test_no_llm_falls_back_to_neg_ratio(self):
        # Without LLM data, should behave like _neg_ratio_risk
        assert self.fn(0.6, None) == 80.0
        assert self.fn(None, None) == 40.0
        assert self.fn(0.05, None) == 20.0

    def test_llm_very_bullish(self):
        # sentiment=100 -> llm_risk=0, neg_ratio=0.5 -> neg_risk=60
        # final = 0*0.6 + 60*0.4 = 24.0
        result = self.fn(0.5, 100.0)
        assert result == 24.0

    def test_llm_very_bearish(self):
        # sentiment=0 -> llm_risk=100, neg_ratio=0.0 -> neg_risk=20
        # final = 100*0.6 + 20*0.4 = 68.0
        result = self.fn(0.0, 0.0)
        assert result == 68.0

    def test_llm_neutral(self):
        # sentiment=50 -> llm_risk=50, neg_ratio=None -> neg_risk=40
        # final = 50*0.6 + 40*0.4 = 46.0
        result = self.fn(None, 50.0)
        assert result == 46.0

    def test_llm_clamped_above_100(self):
        # sentiment=120 should be clamped to 100 -> llm_risk=0
        # neg_ratio=None -> neg_risk=40
        # final = 0*0.6 + 40*0.4 = 16.0
        result = self.fn(None, 120.0)
        assert result == 16.0

    def test_llm_clamped_below_0(self):
        # sentiment=-10 should be clamped to 0 -> llm_risk=100
        # neg_ratio=None -> neg_risk=40
        # final = 100*0.6 + 40*0.4 = 76.0
        result = self.fn(None, -10.0)
        assert result == 76.0

    def test_both_present_blended(self):
        # sentiment=70 -> llm_risk=30, neg_ratio=0.2 -> neg_risk=40
        # final = 30*0.6 + 40*0.4 = 34.0
        result = self.fn(0.2, 70.0)
        assert result == 34.0

    def test_result_always_in_range(self):
        """Ensure output is always between 0 and 100."""
        import random
        random.seed(42)
        for _ in range(100):
            neg_ratio = random.uniform(0, 1) if random.random() > 0.2 else None
            llm = random.uniform(-20, 120) if random.random() > 0.3 else None
            result = self.fn(neg_ratio, llm)
            assert 0.0 <= result <= 100.0, f"Out of range: {result} (neg={neg_ratio}, llm={llm})"


# ---------------------------------------------------------------------------
# Tests for run_announcement_fetch adapter
# ---------------------------------------------------------------------------

class TestRunAnnouncementFetch:
    """Test the scheduler adapter logic."""

    @patch('config.db.execute_query')
    def test_dry_run_does_nothing(self, mock_query):
        from scheduler.adapters import run_announcement_fetch
        run_announcement_fetch(dry_run=True, env='online')
        mock_query.assert_not_called()

    @patch('asyncio.run')
    @patch('api.services.stock_news_service.analyze_stock_news')
    @patch('api.services.stock_news_service.fetch_and_store_news')
    @patch('config.db.execute_query')
    def test_collects_codes_from_tables(self, mock_query, mock_fetch, mock_analyze, mock_asyncio_run):
        """Verify it queries all 3 tables and deduplicates codes."""
        mock_query.side_effect = [
            [{'stock_code': '000001'}, {'stock_code': '000002'}],  # user_positions
            [{'stock_code': '000002'}, {'stock_code': '000003'}],  # user_watchlist
            [{'stock_code': '000003'}, {'stock_code': '000004'}],  # candidate_pool_stocks
        ]
        mock_fetch.return_value = {'fetched': 5, 'new': 2, 'events': 1}
        mock_asyncio_run.return_value = None

        from scheduler.adapters import run_announcement_fetch
        run_announcement_fetch(dry_run=False, env='online')

        # Should have called execute_query 3 times (once per table)
        assert mock_query.call_count == 3
        # Should fetch for 4 unique codes
        assert mock_fetch.call_count == 4

    @patch('asyncio.run')
    @patch('api.services.stock_news_service.analyze_stock_news')
    @patch('api.services.stock_news_service.fetch_and_store_news')
    @patch('config.db.execute_query')
    def test_handles_missing_tables(self, mock_query, mock_fetch, mock_analyze, mock_asyncio_run):
        """If all tables raise exceptions, should log and return without error."""
        mock_query.side_effect = Exception("table does not exist")
        mock_asyncio_run.return_value = None

        from scheduler.adapters import run_announcement_fetch
        # Should not raise
        run_announcement_fetch(dry_run=False, env='online')
        mock_fetch.assert_not_called()

    @patch('asyncio.run')
    @patch('api.services.stock_news_service.analyze_stock_news')
    @patch('api.services.stock_news_service.fetch_and_store_news')
    @patch('config.db.execute_query')
    def test_handles_fetch_failure(self, mock_query, mock_fetch, mock_analyze, mock_asyncio_run):
        """If fetch_and_store_news raises, should continue with next stock."""
        mock_query.side_effect = [
            [{'stock_code': '000001'}, {'stock_code': '000002'}],
            [],
            [],
        ]
        mock_fetch.side_effect = [Exception("network error"), {'fetched': 3, 'new': 1, 'events': 0}]
        mock_asyncio_run.return_value = None

        from scheduler.adapters import run_announcement_fetch
        # Should not raise
        run_announcement_fetch(dry_run=False, env='online')
        assert mock_fetch.call_count == 2

    @patch('asyncio.run')
    @patch('api.services.stock_news_service.analyze_stock_news')
    @patch('api.services.stock_news_service.fetch_and_store_news')
    @patch('config.db.execute_query')
    def test_handles_none_return_from_fetch(self, mock_query, mock_fetch, mock_analyze, mock_asyncio_run):
        """If fetch_and_store_news returns None, should not crash."""
        mock_query.side_effect = [
            [{'stock_code': '000001'}],
            [],
            [],
        ]
        mock_fetch.return_value = None
        mock_asyncio_run.return_value = None

        from scheduler.adapters import run_announcement_fetch
        run_announcement_fetch(dry_run=False, env='online')
        assert mock_fetch.call_count == 1


# ---------------------------------------------------------------------------
# Tests for config constants
# ---------------------------------------------------------------------------

class TestAnnouncementConfig:
    """Verify config constants are valid."""

    def test_weights_sum_to_one(self):
        from data_analyst.risk_assessment.config import (
            ANNOUNCEMENT_LLM_WEIGHT,
            ANNOUNCEMENT_NEG_WEIGHT,
        )
        assert abs(ANNOUNCEMENT_LLM_WEIGHT + ANNOUNCEMENT_NEG_WEIGHT - 1.0) < 1e-9

    def test_lookback_positive(self):
        from data_analyst.risk_assessment.config import ANNOUNCEMENT_LOOKBACK_DAYS
        assert ANNOUNCEMENT_LOOKBACK_DAYS > 0

    def test_weights_in_valid_range(self):
        from data_analyst.risk_assessment.config import (
            ANNOUNCEMENT_LLM_WEIGHT,
            ANNOUNCEMENT_NEG_WEIGHT,
        )
        assert 0.0 < ANNOUNCEMENT_LLM_WEIGHT < 1.0
        assert 0.0 < ANNOUNCEMENT_NEG_WEIGHT < 1.0
