# -*- coding: utf-8 -*-
"""
Embedding model wrapper: Local model service (BGE-large-zh) with DashScope fallback.
"""
import os
import time
import logging
from typing import List, Optional

import httpx
import requests
from openai import OpenAI

from investment_rag.config import RAGConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

# DashScope domains to bypass system proxy (macOS system proxy causes SSL issues)
_DASHSCOPE_DOMAINS = "dashscope.aliyuncs.com"


def _ensure_no_proxy() -> None:
    """Ensure NO_PROXY includes DashScope domains to bypass system proxy."""
    current = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
    if _DASHSCOPE_DOMAINS not in current:
        sep = "," if current else ""
        os.environ["NO_PROXY"] = current + sep + _DASHSCOPE_DOMAINS
        os.environ["no_proxy"] = os.environ["NO_PROXY"]


class EmbeddingClient:
    """Embedding client: local model service first, DashScope API fallback."""

    def __init__(self, config: Optional[RAGConfig] = None):
        _ensure_no_proxy()

        cfg = config or DEFAULT_CONFIG
        self.model = cfg.embedding_model
        self.dimensions = cfg.embedding_dimensions
        self.batch_size = cfg.embedding_batch_size
        self.local_service_url = cfg.local_model_service_url
        self._local_available: Optional[bool] = None
        self._local_fail_time: float = 0

        if not cfg.embedding_api_key:
            raise ValueError("RAG_API_KEY is not set in .env")

        self._dashscope_client = OpenAI(
            api_key=cfg.embedding_api_key,
            base_url=cfg.embedding_base_url,
            http_client=httpx.Client(timeout=30.0),
        )

    def _check_local_service(self) -> bool:
        """Check if local model service is reachable.

        After a failure, retries every 5 minutes to avoid permanent fallback.
        """
        if not self.local_service_url:
            return False
        if self._local_available is False:
            # Retry after 5 minutes
            if time.time() - self._local_fail_time < 300:
                return False
        try:
            resp = requests.get(f"{self.local_service_url}/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

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
        # Try local model service first
        if self._check_local_service():
            try:
                return self._embed_local(texts, text_type)
            except Exception as e:
                logger.warning("Local embedding failed: %s, falling back to DashScope", e)
                self._local_available = False
                self._local_fail_time = time.time()

        # Fallback to DashScope
        return self._embed_dashscope(texts)

    def _embed_local(self, texts: List[str], text_type: str) -> List[List[float]]:
        """Call local model service for embedding."""
        all_embeddings = []
        # Local service accepts up to 64 texts, process in chunks for safety
        for i in range(0, len(texts), 32):
            batch = texts[i:i + 32]
            resp = requests.post(
                f"{self.local_service_url}/embed",
                json={"texts": batch, "text_type": text_type},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("dimensions") != self.dimensions:
                raise ValueError(
                    f"Dimension mismatch: local={data.get('dimensions')}, expected={self.dimensions}"
                )
            all_embeddings.extend(data["embeddings"])

        logger.debug("Local embedding: %d texts, %d dimensions", len(texts), self.dimensions)
        self._local_available = True
        return all_embeddings

    def _embed_dashscope(self, texts: List[str]) -> List[List[float]]:
        """Call DashScope API for embedding (original logic)."""
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            kwargs = {
                "model": self.model,
                "input": batch,
                "dimensions": self.dimensions,
            }
            resp = self._dashscope_client.embeddings.create(**kwargs)
            batch_embeddings = [item.embedding for item in resp.data]
            all_embeddings.extend(batch_embeddings)

        logger.debug("DashScope embedding: %d texts", len(texts))
        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query string."""
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
