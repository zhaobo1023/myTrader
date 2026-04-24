# -*- coding: utf-8 -*-
"""BGE-large-zh embedding service.

Loads BAAI/bge-large-zh-v1.5 model and provides text embedding.
Output dimension: 1024 (matches DashScope text-embedding-v4).
"""
import logging
from typing import List

from sentence_transformers import SentenceTransformer

from model_service.app.config import config

logger = logging.getLogger(__name__)


class EmbeddingService:
    """BGE-large-zh embedding service."""

    def __init__(self):
        self.model: SentenceTransformer | None = None
        self._loaded = False

    def load(self) -> None:
        """Load model into memory."""
        if self._loaded:
            return

        logger.info("Loading BGE-large-zh-v1.5 from %s ...", config.embedding_model_path)
        self.model = SentenceTransformer(
            config.embedding_model_path,
            device="cpu",
        )
        self._loaded = True
        dim = self.model.get_sentence_embedding_dimension()
        logger.info("BGE-large-zh loaded. Dimension=%s", dim)

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self.model is not None

    def embed(self, texts: List[str], text_type: str = "document") -> List[List[float]]:
        """Embed texts.

        Args:
            texts: list of strings to embed.
            text_type: 'document' or 'query'.
                For query, prepend BGE instruction prefix.

        Returns:
            List of 1024-dim float vectors.
        """
        if not self._loaded:
            raise RuntimeError("Embedding model not loaded")

        if text_type == "query":
            texts = [config.bge_query_instruction + t for t in texts]

        embeddings = self.model.encode(
            texts,
            batch_size=8,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()


# Singleton
embedding_service = EmbeddingService()
