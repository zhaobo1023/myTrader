# -*- coding: utf-8 -*-
"""API routes for model service."""
import logging
import psutil
from fastapi import APIRouter, HTTPException

from model_service.app.schemas import (
    EmbedRequest, EmbedResponse,
    SentimentRequest, SentimentResponse,
    HealthResponse,
)
from model_service.app.services.embedding_service import embedding_service
from model_service.app.services.sentiment_service import sentiment_service
from model_service.app.config import config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    """Health check - reports model loading status and memory usage."""
    proc = psutil.Process()
    return HealthResponse(
        status="healthy" if (embedding_service.is_loaded and sentiment_service.is_loaded) else "degraded",
        models={
            "embedding": config.embedding_model_name if embedding_service.is_loaded else "not_loaded",
            "sentiment": "xlm-roberta-sentiment" if sentiment_service.is_loaded else "not_loaded",
        },
        memory_mb=round(proc.memory_info().rss / 1024 / 1024, 1),
    )


@router.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    """Generate embeddings for a list of texts."""
    if not embedding_service.is_loaded:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    try:
        embeddings = embedding_service.embed(req.texts, req.text_type)
        return EmbedResponse(
            embeddings=embeddings,
            dimensions=len(embeddings[0]) if embeddings else 0,
            model=config.embedding_model_name,
            count=len(embeddings),
        )
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sentiment", response_model=SentimentResponse)
def sentiment(req: SentimentRequest):
    """Analyze sentiment of news text."""
    if not sentiment_service.is_loaded:
        raise HTTPException(status_code=503, detail="Sentiment model not loaded")

    try:
        sentiment_label, confidence, strength = sentiment_service.analyze(
            title=req.title,
            content=req.content or "",
        )
        return SentimentResponse(
            sentiment=sentiment_label,
            confidence=confidence,
            sentiment_strength=strength,
        )
    except Exception as e:
        logger.error("Sentiment analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
