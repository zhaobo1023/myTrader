# -*- coding: utf-8 -*-
"""
Investment RAG configuration.
"""
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import dotenv_values
import os


@dataclass
class RAGConfig:
    """RAG system configuration."""

    # --- Embedding ---
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_api_key: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_batch_size: int = 10  # API limit is 10

    # --- LLM ---
    llm_model: str = "qwen3-max"
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # --- Reranker ---
    reranker_model: str = "gte-reranker-v2"
    reranker_api_key: str = ""
    reranker_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # --- ChromaDB ---
    chroma_persist_dir: str = ""

    # --- Chunking ---
    chunk_size: int = 800
    chunk_overlap: int = 150

    # --- Retrieval ---
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    rrf_k: int = 60
    dense_top_k: int = 20
    bm25_top_k: int = 20
    final_top_k: int = 5

    # --- Collections ---
    collections: list = field(default_factory=lambda: [
        "reports", "announcements", "notes", "macro"
    ])

    # --- Research data paths ---
    research_dir: str = ""

    def __post_init__(self):
        if not self.chroma_persist_dir:
            self.chroma_persist_dir = str(
                Path(__file__).parent.parent / "data" / "chroma_db"
            )
        if not self.research_dir:
            home = Path.home()
            self.research_dir = str(
                home / "Documents" / "notes" / "Finance" / "Research"
            )


def load_config() -> RAGConfig:
    """Load config from .env file."""
    _env_path = Path(__file__).parent.parent / '.env'
    _env = dotenv_values(_env_path)

    # Allow env vars to override .env
    api_key = os.getenv('RAG_API_KEY', _env.get('RAG_API_KEY', ''))

    return RAGConfig(
        embedding_model=os.getenv('RAG_EMBEDDING_MODEL', _env.get('RAG_EMBEDDING_MODEL', 'text-embedding-v4')),
        embedding_api_key=api_key,
        embedding_base_url=os.getenv('RAG_EMBEDDING_BASE_URL', _env.get('RAG_EMBEDDING_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')),
        embedding_dimensions=int(os.getenv('RAG_EMBEDDING_DIMENSIONS', _env.get('RAG_EMBEDDING_DIMENSIONS', '1024'))),
        llm_model=os.getenv('RAG_LLM_MODEL', _env.get('RAG_LLM_MODEL', 'qwen3-max')),
        llm_api_key=api_key,
        llm_base_url=os.getenv('RAG_LLM_BASE_URL', _env.get('RAG_LLM_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')),
        reranker_model=os.getenv('RAG_RERANKER_MODEL', _env.get('RAG_RERANKER_MODEL', 'gte-reranker-v2')),
        reranker_api_key=api_key,
        reranker_base_url=os.getenv('RAG_RERANKER_BASE_URL', _env.get('RAG_RERANKER_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')),
        chroma_persist_dir=os.getenv('CHROMA_PERSIST_DIR') or _env.get('CHROMA_PERSIST_DIR', ''),
        research_dir=os.getenv('RAG_RESEARCH_DIR', _env.get('RAG_RESEARCH_DIR', '')),
    )


# Default singleton
DEFAULT_CONFIG = load_config()
