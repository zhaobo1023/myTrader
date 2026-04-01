# -*- coding: utf-8 -*-
"""
Batch ingestion pipeline: parse files -> chunk -> embed -> store in ChromaDB + BM25.
"""
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from investment_rag.config import RAGConfig, DEFAULT_CONFIG
from investment_rag.embeddings.embed_model import EmbeddingClient
from investment_rag.store.chroma_client import ChromaClient
from investment_rag.retrieval.bm25_retriever import BM25Retriever
from investment_rag.ingest.parsers.pdf_parser import PDFParser, Chunk
from investment_rag.ingest.parsers.md_parser import MarkdownParser

logger = logging.getLogger(__name__)


class IngestPipeline:
    """End-to-end document ingestion pipeline."""

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        embed_client: Optional[EmbeddingClient] = None,
        chroma_client: Optional[ChromaClient] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
    ):
        cfg = config or DEFAULT_CONFIG
        self.config = cfg
        self.embed_client = embed_client or EmbeddingClient(cfg)
        self.chroma_client = chroma_client or ChromaClient(cfg)
        self.bm25_retriever = bm25_retriever or BM25Retriever(
            k1=cfg.bm25_k1, b=cfg.bm25_b,
        )
        self.pdf_parser = PDFParser(chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap)
        self.md_parser = MarkdownParser(chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap)

    def _parse_file(self, file_path: str) -> List[Chunk]:
        """Parse a single file into chunks based on extension."""
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            return self.pdf_parser.parse_file(file_path)
        elif ext in (".md", ".markdown"):
            return self.md_parser.parse_file(file_path)
        else:
            logger.warning("Unsupported file type: %s", ext)
            return []

    def ingest_paths(
        self,
        paths: List[str],
        collection: str = "reports",
    ) -> Dict[str, Any]:
        """Ingest files or directories.

        Args:
            paths: List of file or directory paths.
            collection: Target collection name.

        Returns:
            Dict with status, files_processed, chunks_created, errors.
        """
        all_chunks = []
        files_processed = 0
        errors = []

        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                errors.append(f"Path not found: {path_str}")
                continue

            if path.is_dir():
                # Recursively find all PDF and MD files
                for ext in ("*.pdf", "*.md", "*.markdown"):
                    for file_path in sorted(path.rglob(ext)):
                        try:
                            chunks = self._parse_file(str(file_path))
                            all_chunks.extend(chunks)
                            files_processed += 1
                            logger.info("Parsed %d chunks from %s", len(chunks), file_path.name)
                        except Exception as e:
                            errors.append(f"{file_path.name}: {e}")
                            logger.error("Failed to parse %s: %s", file_path, e)
            else:
                try:
                    chunks = self._parse_file(str(path))
                    all_chunks.extend(chunks)
                    files_processed += 1
                except Exception as e:
                    errors.append(f"{path.name}: {e}")
                    logger.error("Failed to parse %s: %s", path, e)

        if not all_chunks:
            return {
                "status": "no_chunks",
                "files_processed": files_processed,
                "chunks_created": 0,
                "errors": errors,
            }

        # Embed all chunks
        logger.info("Embedding %d chunks...", len(all_chunks))
        texts = [c.text for c in all_chunks]
        try:
            embeddings = self.embed_client.embed_texts(texts)
        except Exception as e:
            logger.error("Embedding failed: %s", e)
            return {
                "status": "embedding_failed",
                "files_processed": files_processed,
                "chunks_created": 0,
                "errors": [f"Embedding error: {e}"] + errors,
            }

        # Store in ChromaDB
        ids = [c.chunk_id for c in all_chunks]
        metadatas = []
        for c in all_chunks:
            meta = {
                "source": c.source,
                "page": c.page,
            }
            meta.update(c.metadata)
            # ChromaDB does not accept empty list values in metadata
            meta = {k: v for k, v in meta.items() if not (isinstance(v, list) and len(v) == 0)}
            metadatas.append(meta)

        self.chroma_client.add_documents(
            collection_name=collection,
            ids=ids,
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Build BM25 index
        bm25_docs = [
            {"id": c.chunk_id, "text": c.text, "metadata": metadatas[i]}
            for i, c in enumerate(all_chunks)
        ]
        self.bm25_retriever.build_index(collection, bm25_docs)

        logger.info(
            "Ingestion complete: %d files, %d chunks into '%s'",
            files_processed, len(all_chunks), collection,
        )

        return {
            "status": "ok",
            "files_processed": files_processed,
            "chunks_created": len(all_chunks),
            "errors": errors,
        }
