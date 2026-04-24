# -*- coding: utf-8 -*-
"""Model service configuration."""
import os
from pathlib import Path


class ModelServiceConfig:
    """Configuration for local model service."""

    def __init__(self):
        self.model_base_dir = os.getenv("MODEL_BASE_DIR", str(Path.home() / ".cache" / "mytrader_models"))
        self.embedding_model_name = os.getenv("EMBEDDING_MODEL_NAME", "bge-large-zh-v1.5")
        self.sentiment_model_name = os.getenv(
            "SENTIMENT_MODEL_NAME",
            "cardiffnlp/twitter-xlm-roberta-base-sentiment-multilingual",
        )
        self.embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
        # BGE query prefix for Chinese retrieval
        self.bge_query_instruction = "\u4e3a\u8fd9\u4e2a\u53e5\u5b50\u751f\u6210\u8868\u793a\u4ee5\u7528\u4e8e\u68c0\u7d22\u76f8\u5173\u6587\u7ae0\uff1a"

    @property
    def embedding_model_path(self) -> str:
        return str(Path(self.model_base_dir) / self.embedding_model_name)

    @property
    def sentiment_model_path(self) -> str:
        return str(Path(self.model_base_dir) / "xlm-roberta-sentiment")


config = ModelServiceConfig()
