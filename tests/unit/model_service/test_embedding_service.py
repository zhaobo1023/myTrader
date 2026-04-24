# -*- coding: utf-8 -*-
"""Unit tests for EmbeddingService — mock SentenceTransformer, no GPU/models needed."""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from model_service.app.services.embedding_service import EmbeddingService


class TestEmbeddingServiceInit:
    """Test initialization and loading state."""

    def test_initial_state(self):
        svc = EmbeddingService()
        assert svc.model is None
        assert svc._loaded is False
        assert svc.is_loaded is False

    @patch("model_service.app.services.embedding_service.SentenceTransformer")
    def test_load_success(self, MockST):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        MockST.return_value = mock_model

        svc = EmbeddingService()
        svc.load()

        assert svc._loaded is True
        assert svc.is_loaded is True
        assert svc.model is mock_model

    @patch("model_service.app.services.embedding_service.SentenceTransformer")
    def test_load_idempotent(self, MockST):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        MockST.return_value = mock_model

        svc = EmbeddingService()
        svc.load()
        svc.load()  # second call should be no-op

        assert MockST.call_count == 1


class TestEmbeddingServiceEmbed:
    """Test embedding logic with mocked model."""

    def _make_loaded_service(self):
        """Create a loaded service with a mock model."""
        svc = EmbeddingService()
        svc.model = MagicMock()
        svc._loaded = True
        # Return a (2, 1024) numpy array
        svc.model.encode.return_value = np.random.rand(2, 1024).astype(np.float32)
        return svc

    def test_embed_not_loaded_raises(self):
        svc = EmbeddingService()
        with pytest.raises(RuntimeError, match="not loaded"):
            svc.embed(["test"])

    def test_embed_document(self):
        svc = self._make_loaded_service()
        result = svc.embed(["hello", "world"], text_type="document")

        assert len(result) == 2
        assert len(result[0]) == 1024
        svc.model.encode.assert_called_once()
        # Should NOT prepend instruction for document
        call_args = svc.model.encode.call_args[0][0]
        assert call_args == ["hello", "world"]

    def test_embed_query_prepends_instruction(self):
        svc = self._make_loaded_service()
        result = svc.embed(["测试查询"], text_type="query")

        call_args = svc.model.encode.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].endswith("测试查询")
        assert "检索" in call_args[0]  # BGE Chinese instruction contains 检索

    def test_embed_returns_list_of_lists(self):
        svc = self._make_loaded_service()
        result = svc.embed(["a"])

        assert isinstance(result, list)
        assert isinstance(result[0], list)
        assert isinstance(result[0][0], float)
