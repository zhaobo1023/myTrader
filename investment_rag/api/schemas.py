# -*- coding: utf-8 -*-
"""
Pydantic schemas for the Investment RAG API.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Query request."""
    query: str = Field(..., description="User query text", min_length=1)
    collection: Optional[str] = Field(
        None, description="Target collection (reports/announcements/notes/macro)",
    )
    top_k: Optional[int] = Field(5, description="Number of results", ge=1, le=50)


class QueryResult(BaseModel):
    """A single query result."""
    id: str
    text: str
    metadata: Dict[str, Any] = {}
    score: float = 0.0
    source: str = ""


class QueryResponse(BaseModel):
    """Query response."""
    query: str
    intent: str = "rag"
    collection: str = "reports"
    results: List[QueryResult] = []
    sql: Optional[str] = None
    sql_results: Optional[List[Dict[str, Any]]] = None


class IngestRequest(BaseModel):
    """Ingestion request."""
    paths: List[str] = Field(..., description="File or directory paths to ingest")
    collection: str = Field("reports", description="Target collection")


class IngestResponse(BaseModel):
    """Ingestion response."""
    status: str
    files_processed: int = 0
    chunks_created: int = 0
    errors: List[str] = []


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    collections: Dict[str, int] = {}
