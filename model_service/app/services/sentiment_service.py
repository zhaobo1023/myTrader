# -*- coding: utf-8 -*-
"""Sentiment analysis service using multilingual XLM-RoBERTa.

Supports Chinese financial news sentiment classification.
Output: positive / negative / neutral + confidence.
"""
import logging
from typing import Tuple

from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

from model_service.app.config import config

logger = logging.getLogger(__name__)

_LABEL_MAP = {
    "negative": "negative",
    "neutral": "neutral",
    "positive": "positive",
}


class SentimentService:
    """Multilingual sentiment classification service."""

    def __init__(self):
        self.classifier = None
        self._loaded = False

    def load(self) -> None:
        """Load model into memory."""
        if self._loaded:
            return

        model_path = config.sentiment_model_path
        logger.info("Loading sentiment model from %s ...", model_path)

        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.classifier = pipeline(
            "sentiment-analysis",
            model=model,
            tokenizer=tokenizer,
            device=-1,  # CPU
            top_k=None,  # return all scores
        )
        self._loaded = True
        logger.info("Sentiment model loaded.")

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self.classifier is not None

    def analyze(self, title: str, content: str = "") -> Tuple[str, float, int]:
        """Analyze sentiment of text.

        Args:
            title: news title.
            content: news body (optional).

        Returns:
            (sentiment, confidence, strength)
            - sentiment: "positive" | "negative" | "neutral"
            - confidence: 0.0 - 1.0
            - strength: 1-5
        """
        if not self._loaded:
            raise RuntimeError("Sentiment model not loaded")

        text = f"{title} {content}".strip()[:512]  # truncate to model max length
        scores = self.classifier(text)[0]  # list of {label, score}

        # Build label -> score dict
        score_map = {}
        for item in scores:
            label = item["label"].lower()
            if label in _LABEL_MAP:
                score_map[_LABEL_MAP[label]] = item["score"]

        # Pick top sentiment
        sentiment = max(score_map, key=score_map.get) if score_map else "neutral"
        confidence = score_map.get(sentiment, 0.5)

        # Map confidence to strength 1-5
        if confidence < 0.4:
            strength = 1
        elif confidence < 0.55:
            strength = 2
        elif confidence < 0.7:
            strength = 3
        elif confidence < 0.85:
            strength = 4
        else:
            strength = 5

        return sentiment, confidence, strength


# Singleton
sentiment_service = SentimentService()
