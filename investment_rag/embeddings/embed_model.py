# -*- coding: utf-8 -*-
"""
Embedding model wrapper: DashScope text-embedding-v4 via OpenAI SDK.

Also provides LLM client for Qwen3 generation (for future use).
"""
import os
import logging
from typing import List, Optional

import httpx
from openai import OpenAI

from investment_rag.config import RAGConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

# DashScope domains to bypass system proxy (macOS system proxy causes SSL issues)
_DASHSCOPE_DOMAINS = "dashscope.aliyuncs.com"


def _ensure_no_proxy() -> None:
    """Ensure NO_PROXY includes DashScope domains to bypass system proxy.

    macOS system proxy (e.g. Clash/Surge) intercepts HTTPS traffic and causes
    SSL handshake failures with LibreSSL. Setting NO_PROXY avoids this.
    """
    current = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
    if _DASHSCOPE_DOMAINS not in current:
        sep = "," if current else ""
        os.environ["NO_PROXY"] = current + sep + _DASHSCOPE_DOMAINS
        os.environ["no_proxy"] = os.environ["NO_PROXY"]


class EmbeddingClient:
    """Wrapper for DashScope embedding API (OpenAI-compatible)."""

    def __init__(self, config: Optional[RAGConfig] = None):
        _ensure_no_proxy()

        cfg = config or DEFAULT_CONFIG
        self.model = cfg.embedding_model
        self.dimensions = cfg.embedding_dimensions
        self.batch_size = cfg.embedding_batch_size

        if not cfg.embedding_api_key:
            raise ValueError("RAG_API_KEY is not set in .env")

        self.client = OpenAI(
            api_key=cfg.embedding_api_key,
            base_url=cfg.embedding_base_url,
            http_client=httpx.Client(timeout=30.0),
        )

    def embed_texts(
        self,
        texts: List[str],
        text_type: str = "document",
        instruct: Optional[str] = None,
    ) -> List[List[float]]:
        """Embed a list of texts.

        Args:
            texts: List of text strings to embed.
            text_type: 'document' for indexing, 'query' for searching.
            instruct: Optional task instruction for query embedding.

        Returns:
            List of embedding vectors.
        """
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            kwargs = {
                "model": self.model,
                "input": batch,
                "dimensions": self.dimensions,
            }
            # text_type and instruct are only supported via DashScope SDK,
            # not via OpenAI compatible API. We skip them here.
            resp = self.client.embeddings.create(**kwargs)
            batch_embeddings = [item.embedding for item in resp.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query string.

        Args:
            query: The search query.

        Returns:
            Single embedding vector.
        """
        results = self.embed_texts([query], text_type="query")
        return results[0]


class LLMClient:
    """Wrapper for Qwen3 LLM via OpenAI SDK."""

    def __init__(self, config: Optional[RAGConfig] = None):
        _ensure_no_proxy()

        cfg = config or DEFAULT_CONFIG
        self.model = cfg.llm_model

        if not cfg.llm_api_key:
            raise ValueError("RAG_API_KEY is not set in .env")

        self.client = OpenAI(
            api_key=cfg.llm_api_key,
            base_url=cfg.llm_base_url,
            http_client=httpx.Client(timeout=60.0),
        )

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Max tokens in response.

        Returns:
            Generated text.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
