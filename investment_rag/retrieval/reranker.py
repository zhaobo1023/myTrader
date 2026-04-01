# -*- coding: utf-8 -*-
"""
Reranker using DashScope gte-reranker-v2 API.

Takes top-N results from hybrid retrieval and re-ranks them
using a cross-encoder model.
"""
import logging
from typing import List, Dict, Any, Optional

import httpx
from openai import OpenAI

from investment_rag.config import RAGConfig, DEFAULT_CONFIG
from investment_rag.embeddings.embed_model import _ensure_no_proxy

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder reranker via DashScope API."""

    def __init__(self, config: Optional[RAGConfig] = None):
        _ensure_no_proxy()

        cfg = config or DEFAULT_CONFIG
        self.model = cfg.reranker_model

        if not cfg.reranker_api_key:
            logger.warning("RAG_API_KEY not set, reranker disabled")
            self.enabled = False
            return

        self.enabled = True
        self.client = OpenAI(
            api_key=cfg.reranker_api_key,
            base_url=cfg.reranker_base_url,
            http_client=httpx.Client(timeout=30.0),
        )

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Re-rank documents for a query.

        Args:
            query: The search query.
            documents: List of result dicts with 'text' field.
            top_k: Number of results to return.

        Returns:
            Re-ranked results with added 'rerank_score' field.
        """
        if not self.enabled or not documents:
            return documents[:top_k]

        if len(documents) <= top_k:
            return documents

        # Build query-document pairs for reranking
        # Use DashScope-compatible rerank API
        texts = [doc["text"] for doc in documents]

        try:
            resp = self.client.rerank(
                model=self.model,
                query=query,
                documents=texts,
                top_n=top_k,
            )

            results = []
            for item in resp.data:
                idx = item.index
                result = dict(documents[idx])
                result["rerank_score"] = item.relevance_score
                results.append(result)

            return results

        except Exception as e:
            logger.error("Reranking failed: %s, falling back to original order", e)
            return documents[:top_k]
