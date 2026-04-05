# -*- coding: utf-8 -*-
"""
RAG schemas
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question")
    collection: Optional[str] = Field(default=None, description="Collection name")
    top_k: int = Field(default=5, ge=1, le=20)


class RAGSource(BaseModel):
    source: str
    text: str
    score: float
    metadata: dict = {}


class RAGQueryResponse(BaseModel):
    query: str
    intent: str
    answer: str
    sources: List[RAGSource] = []
    sql_results: Optional[list] = None
