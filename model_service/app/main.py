# -*- coding: utf-8 -*-
"""Model service FastAPI application.

Loads BGE-large-zh and XLM-RoBERTa sentiment models at startup,
exposes /health, /embed, /sentiment endpoints.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from model_service.app.routes.routes import router
from model_service.app.services.embedding_service import embedding_service
from model_service.app.services.sentiment_service import sentiment_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup."""
    logger.info("=== Model Service Starting ===")

    # Load models sequentially to avoid memory spike
    try:
        embedding_service.load()
    except Exception as e:
        logger.error("Failed to load embedding model: %s", e)

    try:
        sentiment_service.load()
    except Exception as e:
        logger.error("Failed to load sentiment model: %s", e)

    logger.info("=== Model Service Ready ===")
    yield

    logger.info("=== Model Service Shutting Down ===")


app = FastAPI(
    title="myTrader Model Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
