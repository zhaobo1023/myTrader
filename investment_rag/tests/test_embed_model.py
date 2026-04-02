# -*- coding: utf-8 -*-
"""Unit tests for embedding model wrapper."""
import os
import pytest

from investment_rag.config import load_config, RAGConfig
from investment_rag.embeddings.embed_model import EmbeddingClient, LLMClient


class TestEmbeddingClient:
    """Tests that require the actual DashScope API."""

    def setup_method(self):
        config = load_config()
        if not config.embedding_api_key:
            pytest.skip("RAG_API_KEY not set")
        self.client = EmbeddingClient(config)

    def test_embed_single_text(self):
        result = self.client.embed_texts(["This is a test sentence."])
        assert len(result) == 1
        assert len(result[0]) == self.client.dimensions
        assert isinstance(result[0][0], float)

    def test_embed_chinese_text(self):
        result = self.client.embed_texts(["中国核电产业发展前景分析"])
        assert len(result) == 1
        assert len(result[0]) == self.client.dimensions

    def test_embed_batch(self):
        texts = [
            "First document about coal industry.",
            "Second document about chemical industry.",
            "Third document about tech sector.",
        ]
        result = self.client.embed_texts(texts)
        assert len(result) == 3
        for vec in result:
            assert len(vec) == self.client.dimensions

    def test_embed_query(self):
        result = self.client.embed_query("What is the outlook for coal stocks?")
        assert len(result) == self.client.dimensions
        assert isinstance(result[0], float)

    def test_empty_texts(self):
        result = self.client.embed_texts([])
        assert result == []

    def test_config_no_key(self):
        cfg = RAGConfig(embedding_api_key="")
        with pytest.raises(ValueError, match="RAG_API_KEY"):
            EmbeddingClient(cfg)


class TestLLMClient:
    """Tests for Qwen3 LLM client."""

    def setup_method(self):
        config = load_config()
        if not config.llm_api_key:
            pytest.skip("RAG_API_KEY not set")
        self.client = LLMClient(config)

    def test_generate_simple(self):
        result = self.client.generate("Say hello in Chinese.")
        assert result is not None
        assert len(result) > 0

    def test_generate_with_system(self):
        result = self.client.generate(
            "What is 1+1?",
            system_prompt="You are a helpful assistant. Answer concisely.",
            temperature=0.0,
        )
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
