# -*- coding: utf-8 -*-
"""
Golden test set evaluation: Recall@K, Precision@K, MRR.

Usage:
    python -m investment_rag.tests.eval_metrics
"""
import json
import os
import logging
from typing import List, Dict, Any

from investment_rag.retrieval.hybrid_retriever import HybridRetriever
from investment_rag.config import load_config

logger = logging.getLogger(__name__)

GOLDEN_SET_PATH = os.path.join(
    os.path.dirname(__file__), "golden_set.json"
)


def load_golden_set() -> List[Dict[str, Any]]:
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def recall_at_k(
    results: List[Dict[str, Any]],
    expected_sources: List[str],
    k: int = 5,
) -> float:
    """Compute Recall@K: fraction of expected sources found in top-K results."""
    if not expected_sources:
        return 0.0

    top_k_results = results[:k]
    retrieved_sources = set()
    for r in top_k_results:
        source = r.get("metadata", {}).get("source", r.get("source", ""))
        if source:
            retrieved_sources.add(source)

    hits = sum(1 for exp in expected_sources if any(exp in s for s in retrieved_sources))
    return hits / len(expected_sources)


def precision_at_k(
    results: List[Dict[str, Any]],
    expected_sources: List[str],
    k: int = 5,
) -> float:
    """Compute Precision@K: fraction of top-K results that are relevant."""
    if not results or k == 0:
        return 0.0

    top_k_results = results[:k]
    relevant = 0
    for r in top_k_results:
        source = r.get("metadata", {}).get("source", r.get("source", ""))
        if source and any(exp in source for exp in expected_sources):
            relevant += 1

    return relevant / min(k, len(top_k_results))


def mrr(
    results: List[Dict[str, Any]],
    expected_sources: List[str],
) -> float:
    """Compute Mean Reciprocal Rank: 1/rank of first relevant result."""
    for rank, r in enumerate(results, start=1):
        source = r.get("metadata", {}).get("source", r.get("source", ""))
        if source and any(exp in source for exp in expected_sources):
            return 1.0 / rank
    return 0.0


def run_evaluation(k: int = 5) -> Dict[str, Any]:
    """Run evaluation on the golden test set.

    Returns:
        Dict with per-query and aggregate metrics.
    """
    golden_set = load_golden_set()
    config = load_config()

    if not config.embedding_api_key:
        logger.error("RAG_API_KEY not set, cannot run evaluation")
        return {"error": "RAG_API_KEY not set"}

    retriever = HybridRetriever(config=config)
    results = []

    total_recall = 0.0
    total_precision = 0.0
    total_mrr = 0.0
    evaluated = 0

    for case in golden_set:
        query = case["query"]
        collection = case.get("collection", "reports")
        expected_sources = case.get("expected_sources", [])

        try:
            hits = retriever.retrieve(query, collection=collection, top_k=k)
        except Exception as e:
            logger.error("Query '%s' failed: %s", query, e)
            hits = []

        r = recall_at_k(hits, expected_sources, k)
        p = precision_at_k(hits, expected_sources, k)
        m = mrr(hits, expected_sources)

        total_recall += r
        total_precision += p
        total_mrr += m
        evaluated += 1

        case_result = {
            "id": case["id"],
            "query": query,
            "recall": round(r, 4),
            "precision": round(p, 4),
            "mrr": round(m, 4),
            "num_results": len(hits),
        }
        results.append(case_result)

        logger.info(
            "[%s] R@%d=%.2f P@%d=%.2f MRR=%.2f - %s",
            case["id"], k, r, k, p, m, query[:40],
        )

    if evaluated == 0:
        return {"error": "No queries evaluated"}

    return {
        "aggregate": {
            f"recall@{k}": round(total_recall / evaluated, 4),
            f"precision@{k}": round(total_precision / evaluated, 4),
            "mrr": round(total_mrr / evaluated, 4),
            "num_queries": evaluated,
        },
        "per_query": results,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_evaluation()
    print(json.dumps(result, indent=2, ensure_ascii=False))
