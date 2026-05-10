# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - LLM Model Configuration

Stores per-scene LLM model settings that can be switched at runtime.
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text

from api.dependencies import Base


class LLMModelConfig(Base):
    __tablename__ = 'llm_model_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Usage scene: agent_chat, rag_query, skill, report, daily_report, etc.
    scene = Column(String(64), nullable=False, unique=True, comment='Usage scene identifier')
    # Model alias for display
    alias = Column(String(64), nullable=False, comment='Model alias e.g. qwen, deepseek')
    # Actual model name passed to API
    model = Column(String(128), nullable=False, comment='Model name e.g. qwen3.6-plus, deepseek-chat')
    # API base URL
    base_url = Column(String(512), nullable=False)
    # Env var name holding the API key
    api_key_env = Column(String(64), nullable=False)
    # Whether this is the default config for the scene
    is_default = Column(Boolean, nullable=False, default=False)
    # Whether this config is active
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
