# -*- coding: utf-8 -*-
"""Unit tests for Pydantic schemas — request validation."""
import pytest
from pydantic import ValidationError

from model_service.app.schemas import EmbedRequest, SentimentRequest


class TestEmbedRequest:
    def test_valid_document(self):
        req = EmbedRequest(texts=["hello"])
        assert req.text_type == "document"

    def test_valid_query(self):
        req = EmbedRequest(texts=["search"], text_type="query")
        assert req.text_type == "query"

    def test_empty_texts_rejected(self):
        with pytest.raises(ValidationError):
            EmbedRequest(texts=[])

    def test_too_many_texts_rejected(self):
        with pytest.raises(ValidationError):
            EmbedRequest(texts=["t"] * 65)

    def test_max_texts_accepted(self):
        req = EmbedRequest(texts=["t"] * 64)
        assert len(req.texts) == 64

    def test_invalid_text_type_rejected(self):
        with pytest.raises(ValidationError):
            EmbedRequest(texts=["test"], text_type="unknown")


class TestSentimentRequest:
    def test_valid_minimal(self):
        req = SentimentRequest(title="新闻标题")
        assert req.content is None
        assert req.stock_code is None

    def test_valid_full(self):
        req = SentimentRequest(title="标题", content="内容", stock_code="600519")
        assert req.content == "内容"

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            SentimentRequest(title="")

    def test_missing_title_rejected(self):
        with pytest.raises(ValidationError):
            SentimentRequest()
