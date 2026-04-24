# -*- coding: utf-8 -*-
"""Unit tests for model service API routes — test via FastAPI TestClient."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _patch_services():
    """Patch singletons in the routes module where they are actually used."""
    with patch("model_service.app.routes.routes.embedding_service") as mock_embed, \
         patch("model_service.app.routes.routes.sentiment_service") as mock_sentiment:
        # Default: both loaded
        type(mock_embed).is_loaded = PropertyMock(return_value=True)
        type(mock_sentiment).is_loaded = PropertyMock(return_value=True)
        mock_embed.embed.return_value = [[0.1] * 1024]
        mock_sentiment.analyze.return_value = ("neutral", 0.5, 3)
        yield {"embed": mock_embed, "sentiment": mock_sentiment}


@pytest.fixture
def client():
    from model_service.app.main import app
    return TestClient(app)


class TestHealthEndpoint:
    def test_healthy(self, client, _patch_services):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "memory_mb" in data

    def test_degraded_when_embedding_not_loaded(self, client, _patch_services):
        type(_patch_services["embed"]).is_loaded = PropertyMock(return_value=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"


class TestEmbedEndpoint:
    def test_embed_success(self, client, _patch_services):
        _patch_services["embed"].embed.return_value = [[0.1] * 1024, [0.2] * 1024]
        resp = client.post("/embed", json={
            "texts": ["hello", "world"],
            "text_type": "document",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["dimensions"] == 1024
        assert data["count"] == 2

    def test_embed_model_not_loaded(self, client, _patch_services):
        type(_patch_services["embed"]).is_loaded = PropertyMock(return_value=False)
        resp = client.post("/embed", json={"texts": ["test"]})
        assert resp.status_code == 503

    def test_embed_empty_texts_rejected(self, client, _patch_services):
        resp = client.post("/embed", json={"texts": []})
        assert resp.status_code == 422

    def test_embed_invalid_text_type(self, client, _patch_services):
        resp = client.post("/embed", json={"texts": ["test"], "text_type": "invalid"})
        assert resp.status_code == 422

    def test_embed_internal_error(self, client, _patch_services):
        _patch_services["embed"].embed.side_effect = RuntimeError("boom")
        resp = client.post("/embed", json={"texts": ["test"]})
        assert resp.status_code == 500


class TestSentimentEndpoint:
    def test_sentiment_success(self, client, _patch_services):
        _patch_services["sentiment"].analyze.return_value = ("positive", 0.85, 4)
        resp = client.post("/sentiment", json={
            "title": "利好消息",
            "content": "公司业绩超预期",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["sentiment"] == "positive"
        assert data["confidence"] == 0.85
        assert data["sentiment_strength"] == 4

    def test_sentiment_model_not_loaded(self, client, _patch_services):
        type(_patch_services["sentiment"]).is_loaded = PropertyMock(return_value=False)
        resp = client.post("/sentiment", json={"title": "test"})
        assert resp.status_code == 503

    def test_sentiment_empty_title_rejected(self, client, _patch_services):
        resp = client.post("/sentiment", json={"title": ""})
        assert resp.status_code == 422

    def test_sentiment_optional_fields(self, client, _patch_services):
        _patch_services["sentiment"].analyze.return_value = ("neutral", 0.5, 3)
        resp = client.post("/sentiment", json={"title": "test"})
        assert resp.status_code == 200
