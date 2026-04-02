# -*- coding: utf-8 -*-
"""
Investment RAG - A-share investment research retrieval-augmented generation system.

Modules:
    ingest       - PDF/MD parsing, chunking, batch ingestion
    embeddings   - Qwen3 embedding API wrapper
    store        - ChromaDB vector store, MySQL client
    retrieval    - BM25, hybrid retriever, reranker, intent router, Text2SQL
    generation   - LLM client (reserved)
    api          - FastAPI endpoints
"""
