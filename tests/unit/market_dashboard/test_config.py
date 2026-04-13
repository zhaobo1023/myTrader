# -*- coding: utf-8 -*-
"""Tests for market dashboard config consistency."""
import pytest
from data_analyst.market_dashboard.config import (
    VOLUME_RATIO_THRESHOLDS, VOLUME_RATIO_LEVELS,
    TURNOVER_PCT_THRESHOLDS, TURNOVER_PCT_LEVELS,
    ADV_DEC_RATIO_THRESHOLDS, ADV_DEC_LEVELS,
    MARGIN_CHANGE_THRESHOLDS, MARGIN_CHANGE_LEVELS,
    TEMPERATURE_THRESHOLDS, TEMPERATURE_LEVELS,
    ADX_THRESHOLDS, ADX_LEVELS,
    FEAR_GREED_THRESHOLDS, FEAR_GREED_LEVELS,
    QVIX_THRESHOLDS, QVIX_LEVELS,
    TEMPERATURE_LABELS, TREND_LABELS, FEAR_GREED_LABELS,
    STOCK_BOND_LABELS, MACRO_LABELS, STYLE_LABELS,
)


class TestThresholdConsistency:
    """Verify threshold arrays have correct length relative to label arrays."""

    def test_volume_ratio(self):
        assert len(VOLUME_RATIO_LEVELS) == len(VOLUME_RATIO_THRESHOLDS) + 1

    def test_turnover_pct(self):
        assert len(TURNOVER_PCT_LEVELS) == len(TURNOVER_PCT_THRESHOLDS) + 1

    def test_adv_dec_ratio(self):
        assert len(ADV_DEC_LEVELS) == len(ADV_DEC_RATIO_THRESHOLDS) + 1

    def test_margin_change(self):
        assert len(MARGIN_CHANGE_LEVELS) == len(MARGIN_CHANGE_THRESHOLDS) + 1

    def test_temperature(self):
        assert len(TEMPERATURE_LEVELS) == len(TEMPERATURE_THRESHOLDS) + 1

    def test_adx(self):
        assert len(ADX_LEVELS) == len(ADX_THRESHOLDS) + 1

    def test_fear_greed(self):
        assert len(FEAR_GREED_LEVELS) == len(FEAR_GREED_THRESHOLDS) + 1

    def test_qvix(self):
        assert len(QVIX_LEVELS) == len(QVIX_THRESHOLDS) + 1


class TestLabelsComplete:
    """Verify all levels have a corresponding label."""

    def test_temperature_labels(self):
        for level in TEMPERATURE_LEVELS:
            assert level in TEMPERATURE_LABELS, f"Missing label for temperature level: {level}"

    def test_trend_labels(self):
        from data_analyst.market_dashboard.config import TREND_LEVELS
        for level in TREND_LEVELS:
            assert level in TREND_LABELS, f"Missing label for trend level: {level}"

    def test_fear_greed_labels(self):
        for level in FEAR_GREED_LEVELS:
            assert level in FEAR_GREED_LABELS, f"Missing label for fear_greed level: {level}"


class TestThresholdsAscending:
    """Verify all threshold arrays are in ascending order."""

    @pytest.mark.parametrize("name,thresholds", [
        ("VOLUME_RATIO", VOLUME_RATIO_THRESHOLDS),
        ("TURNOVER_PCT", TURNOVER_PCT_THRESHOLDS),
        ("ADV_DEC_RATIO", ADV_DEC_RATIO_THRESHOLDS),
        ("MARGIN_CHANGE", MARGIN_CHANGE_THRESHOLDS),
        ("TEMPERATURE", TEMPERATURE_THRESHOLDS),
        ("ADX", ADX_THRESHOLDS),
        ("FEAR_GREED", FEAR_GREED_THRESHOLDS),
        ("QVIX", QVIX_THRESHOLDS),
    ])
    def test_ascending(self, name, thresholds):
        for i in range(1, len(thresholds)):
            assert thresholds[i] > thresholds[i - 1], \
                f"{name} thresholds not ascending at index {i}: {thresholds}"
