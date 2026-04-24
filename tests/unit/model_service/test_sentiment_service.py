# -*- coding: utf-8 -*-
"""Unit tests for SentimentService — mock transformers pipeline, no GPU/models needed."""
import pytest
from unittest.mock import patch, MagicMock

from model_service.app.services.sentiment_service import SentimentService


class TestSentimentServiceInit:
    """Test initialization and loading state."""

    def test_initial_state(self):
        svc = SentimentService()
        assert svc.classifier is None
        assert svc._loaded is False
        assert svc.is_loaded is False

    @patch("model_service.app.services.sentiment_service.pipeline")
    @patch("model_service.app.services.sentiment_service.AutoModelForSequenceClassification")
    @patch("model_service.app.services.sentiment_service.AutoTokenizer")
    def test_load_success(self, MockTokenizer, MockModel, MockPipeline):
        MockPipeline.return_value = MagicMock()
        svc = SentimentService()
        svc.load()

        assert svc._loaded is True
        assert svc.is_loaded is True
        MockTokenizer.from_pretrained.assert_called_once()
        MockModel.from_pretrained.assert_called_once()

    @patch("model_service.app.services.sentiment_service.pipeline")
    @patch("model_service.app.services.sentiment_service.AutoModelForSequenceClassification")
    @patch("model_service.app.services.sentiment_service.AutoTokenizer")
    def test_load_idempotent(self, MockTokenizer, MockModel, MockPipeline):
        MockPipeline.return_value = MagicMock()
        svc = SentimentService()
        svc.load()
        svc.load()

        assert MockTokenizer.from_pretrained.call_count == 1


class TestSentimentServiceAnalyze:
    """Test sentiment analysis logic."""

    def _make_loaded_service(self, classifier_result):
        svc = SentimentService()
        svc.classifier = MagicMock()
        svc._loaded = True
        svc.classifier.return_value = [classifier_result]
        return svc

    def test_analyze_not_loaded_raises(self):
        svc = SentimentService()
        with pytest.raises(RuntimeError, match="not loaded"):
            svc.analyze("test")

    def test_analyze_positive(self):
        scores = [
            {"label": "positive", "score": 0.85},
            {"label": "neutral", "score": 0.10},
            {"label": "negative", "score": 0.05},
        ]
        svc = self._make_loaded_service(scores)
        sentiment, confidence, strength = svc.analyze("利好消息")

        assert sentiment == "positive"
        assert confidence == pytest.approx(0.85, abs=0.01)
        assert strength == 5  # 0.85 is not < 0.85, so else → 5

    def test_analyze_negative(self):
        scores = [
            {"label": "negative", "score": 0.90},
            {"label": "neutral", "score": 0.06},
            {"label": "positive", "score": 0.04},
        ]
        svc = self._make_loaded_service(scores)
        sentiment, confidence, strength = svc.analyze("利空消息")

        assert sentiment == "negative"
        assert confidence == pytest.approx(0.90, abs=0.01)
        assert strength == 5

    def test_analyze_neutral(self):
        scores = [
            {"label": "neutral", "score": 0.60},
            {"label": "positive", "score": 0.25},
            {"label": "negative", "score": 0.15},
        ]
        svc = self._make_loaded_service(scores)
        sentiment, confidence, strength = svc.analyze("中性消息")

        assert sentiment == "neutral"
        assert confidence == pytest.approx(0.60, abs=0.01)
        assert strength == 3  # 0.60 < 0.70 → 3

    def test_strength_boundaries(self):
        """Test strength mapping at each boundary."""
        test_cases = [
            (0.30, 1),  # < 0.4
            (0.45, 2),  # < 0.55
            (0.60, 3),  # < 0.70
            (0.80, 4),  # < 0.85
            (0.90, 5),  # >= 0.85
        ]
        for confidence_val, expected_strength in test_cases:
            # positive has highest score so it's the top sentiment
            scores = [
                {"label": "positive", "score": confidence_val},
                {"label": "neutral", "score": (1 - confidence_val) / 2},
                {"label": "negative", "score": (1 - confidence_val) / 2},
            ]
            svc = self._make_loaded_service(scores)
            _, _, strength = svc.analyze("test")
            assert strength == expected_strength, f"confidence={confidence_val} → strength={strength}, expected={expected_strength}"

    def test_analyze_truncates_long_text(self):
        """Long text should be truncated to 512 chars."""
        scores = [{"label": "neutral", "score": 0.8}]
        svc = self._make_loaded_service(scores)
        long_text = "x" * 1000
        svc.analyze(long_text, "")

        call_args = svc.classifier.call_args[0][0]
        assert len(call_args) <= 512

    def test_analyze_combined_title_content(self):
        """Title and content should be concatenated."""
        scores = [{"label": "positive", "score": 0.9}]
        svc = self._make_loaded_service(scores)
        svc.analyze("标题", "正文内容")

        call_args = svc.classifier.call_args[0][0]
        assert "标题" in call_args
        assert "正文内容" in call_args
