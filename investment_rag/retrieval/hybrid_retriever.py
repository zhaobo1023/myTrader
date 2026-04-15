# -*- coding: utf-8 -*-
"""
Hybrid retriever: Dense (ChromaDB) + BM25 + Reciprocal Rank Fusion (RRF).
"""
import logging
from typing import List, Dict, Any, Optional

from investment_rag.embeddings.embed_model import EmbeddingClient
from investment_rag.store.chroma_client import ChromaClient
from investment_rag.retrieval.bm25_retriever import BM25Retriever
from investment_rag.config import RAGConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


def rrf_merge(
    dense_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    k: int = 60,
    top_k: int = 20,
) -> List[Dict[str, Any]]:
    """Merge two ranked lists using Reciprocal Rank Fusion.

    Args:
        dense_results: Dense retrieval results (sorted by relevance).
        bm25_results: BM25 retrieval results (sorted by relevance).
        k: RRF constant (default 60).
        top_k: Number of results to return.

    Returns:
        Merged and re-ranked results.
    """
    scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict[str, Any]] = {}

    for rank, hit in enumerate(dense_results):
        doc_id = hit["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        doc_map[doc_id] = hit

    for rank, hit in enumerate(bm25_results):
        doc_id = hit["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        if doc_id not in doc_map:
            doc_map[doc_id] = hit

    # Sort by RRF score descending
    sorted_ids = sorted(scores.items(), key=lambda x: -x[1])[:top_k]

    results = []
    for doc_id, score in sorted_ids:
        result = dict(doc_map[doc_id])
        result["rrf_score"] = score
        results.append(result)

    return results


class HybridRetriever:
    """Hybrid retriever combining dense and sparse retrieval with RRF."""

    def __init__(
        self,
        embed_client: Optional[EmbeddingClient] = None,
        chroma_client: Optional[ChromaClient] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        config: Optional[RAGConfig] = None,
    ):
        cfg = config or DEFAULT_CONFIG
        self.embed_client = embed_client or EmbeddingClient(cfg)
        self.chroma_client = chroma_client or ChromaClient(cfg)
        self.bm25_retriever = bm25_retriever or BM25Retriever(
            k1=cfg.bm25_k1, b=cfg.bm25_b,
        )
        self.rrf_k = cfg.rrf_k
        self.dense_top_k = cfg.dense_top_k
        self.bm25_top_k = cfg.bm25_top_k
        self.final_top_k = cfg.final_top_k

    def retrieve(
        self,
        query: str,
        collection: str = "reports",
        top_k: Optional[int] = None,
        where: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve documents using hybrid dense + BM25 + RRF.

        When collection is 'reports', also searches 'research' collection
        so user-uploaded documents are included in results.

        Args:
            query: Search query.
            collection: Collection name to search.
            top_k: Final number of results (default: config.final_top_k).
            where: Optional ChromaDB where filter.

        Returns:
            List of result dicts.
        """
        top_k = top_k or self.final_top_k

        # Determine collections to search
        collections = [collection]
        if collection == "reports":
            collections.append("research")

        # 1. Dense retrieval across all target collections
        query_embedding = self.embed_client.embed_query(query)
        all_dense = []
        for coll in collections:
            try:
                results = self.chroma_client.query(
                    collection_name=coll,
                    query_embedding=query_embedding,
                    top_k=self.dense_top_k,
                    where=where,
                )
                all_dense.extend(results)
            except Exception as e:
                logger.warning("Dense retrieval failed for '%s': %s", coll, e)

        # 2. BM25 retrieval across all target collections
        all_bm25 = []
        for coll in collections:
            if self.bm25_retriever.has_index(coll):
                try:
                    results = self.bm25_retriever.search(
                        collection_name=coll,
                        query=query,
                        top_k=self.bm25_top_k,
                    )
                    all_bm25.extend(results)
                except Exception as e:
                    logger.warning("BM25 retrieval failed for '%s': %s", coll, e)

        # 3. RRF merge
        merged = rrf_merge(
            all_dense, all_bm25,
            k=self.rrf_k,
            top_k=top_k,
        )

        return merged
