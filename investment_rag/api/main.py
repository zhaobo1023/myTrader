# -*- coding: utf-8 -*-
"""
FastAPI application for Investment RAG.

Endpoints:
    GET  /health          - Health check
    POST /query           - Hybrid RAG query
    POST /ingest          - Batch document ingestion
"""
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException

from investment_rag.api.schemas import (
    QueryRequest,
    QueryResponse,
    QueryResult,
    IngestRequest,
    IngestResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Investment RAG",
    description="A-share investment research retrieval system",
    version="0.1.0",
)

# Lazy-loaded singletons
_embed_client = None
_chroma_client = None
_bm25_retriever = None
_reranker = None
_hybrid_retriever = None


def _get_hybrid_retriever():
    """Lazy-initialize the hybrid retriever."""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        _hybrid_retriever = HybridRetriever()
    return _hybrid_retriever


def _get_reranker():
    """Lazy-initialize the reranker."""
    global _reranker
    if _reranker is None:
        from investment_rag.retrieval.reranker import Reranker
        _reranker = Reranker()
    return _reranker


def _get_intent_router():
    from investment_rag.retrieval.intent_router import IntentRouter
    return IntentRouter()


def _get_text2sql():
    from investment_rag.retrieval.text2sql import Text2SQL
    return Text2SQL()


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        from investment_rag.store.chroma_client import ChromaClient
        _chroma_client = ChromaClient()
    return _chroma_client


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    try:
        chroma = _get_chroma_client()
        collections = {}
        for name in ["reports", "announcements", "notes", "macro"]:
            try:
                collections[name] = chroma.collection_count(name)
            except Exception:
                collections[name] = -1
        return HealthResponse(collections=collections)
    except Exception as e:
        return HealthResponse(status=f"error: {e}")


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """Query the RAG system.

    Routes to RAG, SQL, or hybrid based on intent detection.
    """
    router = _get_intent_router()
    route = router.route(req.query)

    collection = req.collection or route.collection
    sql_results = None
    sql_query = None
    rag_results = []

    if route.intent == "sql":
        t2s = _get_text2sql()
        sql_results = t2s.execute(req.query)
        return QueryResponse(
            query=req.query,
            intent="sql",
            collection=collection,
            sql_results=sql_results,
            results=[],
        )

    elif route.intent == "hybrid":
        t2s = _get_text2sql()
        sql_results = t2s.execute(req.query)
        # Fall through to RAG with enriched context

    # RAG retrieval
    try:
        retriever = _get_hybrid_retriever()
        hits = retriever.retrieve(
            query=req.query,
            collection=collection,
            top_k=req.top_k,
        )

        # Rerank
        reranker = _get_reranker()
        hits = reranker.rerank(req.query, hits, top_k=req.top_k)

        rag_results = [
            QueryResult(
                id=h["id"],
                text=h["text"],
                metadata=h.get("metadata", {}),
                score=h.get("rerank_score", h.get("rrf_score", 0.0)),
                source=h.get("metadata", {}).get("source", ""),
            )
            for h in hits
        ]
    except Exception as e:
        logger.error("RAG retrieval failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return QueryResponse(
        query=req.query,
        intent=route.intent,
        collection=collection,
        results=rag_results,
        sql_results=sql_results,
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    """Ingest documents into the RAG system."""
    try:
        from investment_rag.ingest.ingest_pipeline import IngestPipeline
        pipeline = IngestPipeline()
        result = pipeline.ingest_paths(req.paths, req.collection)
        return IngestResponse(**result)
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8900)
