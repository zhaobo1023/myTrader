# -*- coding: utf-8 -*-
"""
BM25 sparse retriever using rank_bm25 + jieba for Chinese tokenization.

In-memory index, built from already-ingested text chunks.
"""
import logging
from typing import List, Dict, Any, Optional

import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Retriever:
    """BM25 sparse retrieval with Chinese tokenization."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._indices: Dict[str, BM25Okapi] = {}
        self._documents: Dict[str, List[Dict[str, Any]]] = {}

    def build_index(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
    ) -> None:
        """Build BM25 index for a collection.

        Args:
            collection_name: Name of the collection.
            documents: List of dicts with 'id', 'text', and optionally 'metadata'.
        """
        if not documents:
            return

        tokenized_corpus = []
        for doc in documents:
            tokens = list(jieba.cut(doc["text"]))
            tokenized_corpus.append(tokens)

        self._indices[collection_name] = BM25Okapi(
            tokenized_corpus, k1=self.k1, b=self.b,
        )
        self._documents[collection_name] = documents
        logger.info(
            "BM25 index built for '%s' with %d documents",
            collection_name, len(documents),
        )

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search the BM25 index.

        Args:
            collection_name: Collection to search.
            query: Search query.
            top_k: Number of results.

        Returns:
            List of result dicts with 'id', 'text', 'metadata', 'score'.
        """
        if collection_name not in self._indices:
            logger.warning("BM25 index not found for '%s'", collection_name)
            return []

        index = self._indices[collection_name]
        docs = self._documents[collection_name]
        query_tokens = list(jieba.cut(query))

        scores = index.get_scores(query_tokens)
        top_indices = scores.argsort()[-top_k:][::-1]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            results.append({
                "id": docs[idx]["id"],
                "text": docs[idx]["text"],
                "metadata": docs[idx].get("metadata", {}),
                "score": float(scores[idx]),
            })

        return results

    def has_index(self, collection_name: str) -> bool:
        """Check if an index exists for a collection."""
        return collection_name in self._indices
