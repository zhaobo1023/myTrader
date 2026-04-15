# -*- coding: utf-8 -*-
"""
ChromaDB vector store client.

Collections:
    reports       - sell-side research reports
    announcements - listed company announcements
    notes         - personal research notes
    macro         - macro policy / data text
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb

from investment_rag.config import RAGConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

COLLECTION_NAMES = ["reports", "announcements", "notes", "macro", "research"]


class ChromaClient:
    """Wrapper around ChromaDB for document storage and retrieval."""

    def __init__(self, config: Optional[RAGConfig] = None):
        cfg = config or DEFAULT_CONFIG
        persist_dir = cfg.chroma_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.dimensions = cfg.embedding_dimensions
        self._collections = {}

    def get_collection(self, name: str) -> chromadb.Collection:
        """Get or create a collection."""
        if name not in self._collections:
            self._collections[name] = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    def add_documents(
        self,
        collection_name: str,
        ids: List[str],
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Add documents to a collection.

        Args:
            collection_name: Target collection name.
            ids: Unique document IDs.
            texts: Document texts.
            embeddings: Pre-computed embedding vectors.
            metadatas: Optional metadata for each document.
        """
        if not texts:
            return

        collection = self.get_collection(collection_name)

        # ChromaDB has a batch limit, process in batches of 5000
        batch_size = 5000
        for i in range(0, len(texts), batch_size):
            end = min(i + batch_size, len(texts))
            batch_ids = ids[i:end]
            batch_texts = texts[i:end]
            batch_embeddings = embeddings[i:end]
            batch_metadatas = metadatas[i:end] if metadatas else None

            collection.add(
                ids=batch_ids,
                documents=batch_texts,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
            )

        logger.info(
            "Added %d documents to collection '%s'",
            len(texts), collection_name,
        )

    def query(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 20,
        where: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Query a collection with an embedding vector.

        Args:
            collection_name: Collection to search.
            query_embedding: Query vector.
            top_k: Number of results to return.
            where: Optional ChromaDB where filter.

        Returns:
            List of result dicts with keys: id, text, metadata, distance.
        """
        collection = self.get_collection(collection_name)

        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
        }
        if where:
            kwargs["where"] = where

        results = collection.query(**kwargs)

        hits = []
        if results and results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                hit = {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                }
                hits.append(hit)

        return hits

    def delete_collection(self, name: str) -> None:
        """Delete a collection entirely."""
        if name in self._collections:
            del self._collections[name]
        self.client.delete_collection(name)
        logger.info("Deleted collection '%s'", name)

    def collection_count(self, name: str) -> int:
        """Get document count in a collection."""
        collection = self.get_collection(name)
        return collection.count()

    def list_collections(self) -> List[str]:
        """List all collection names."""
        return [c.name for c in self.client.list_collections()]

    def reset(self) -> None:
        """Reset all collections. Use with caution."""
        self._collections.clear()
        self.client.reset()
        logger.warning("All ChromaDB collections have been reset")
