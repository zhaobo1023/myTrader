# -*- coding: utf-8 -*-
"""Request/response schemas for model service."""
from typing import List, Optional
from pydantic import BaseModel, Field


# --- Embedding ---

class EmbedRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=64)
    text_type: str = Field(default="document", pattern=r"^(document|query)$")


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    dimensions: int
    model: str
    count: int


# --- Sentiment ---

class SentimentRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: Optional[str] = None
    stock_code: Optional[str] = None


class SentimentResponse(BaseModel):
    sentiment: str  # positive / negative / neutral
    confidence: float
    sentiment_strength: int  # 1-5


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    models: dict
    memory_mb: float
