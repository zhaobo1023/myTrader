# -*- coding: utf-8 -*-
"""
LLM Skill base class and metadata definition.

All LLM skills must inherit from LLMSkillBase and implement:
  - meta property  (SkillMeta dataclass)
  - stream(**kwargs) async generator yielding SSE event dicts

SSE event conventions:
  - Every event must have a "type" field
  - The last successful event must have type == "done"
  - Error events have type == "error" and a "message" field
  - Progress events are named: {stage}_{start|progress|done}
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Any


@dataclass
class SkillMeta:
    skill_id: str       # unique identifier, e.g. "theme-create"
    name: str           # display name, e.g. "主题创建"
    version: str        # semver, e.g. "1.0.0"
    description: str
    requires_llm: bool = True
    min_tier: str = "free"   # "free" | "pro"


class LLMSkillBase(ABC):
    """Abstract base for all LLM skills.

    Contract:
    1. stream() must be an async generator
    2. All exceptions inside stream() must be caught and yielded as error events
    3. DB writes should NOT happen inside stream(); the router handles persistence
       after the stream ends
    """

    @property
    @abstractmethod
    def meta(self) -> SkillMeta:
        ...

    @abstractmethod
    async def stream(self, **kwargs: Any) -> AsyncIterator[dict]:
        ...

    async def validate_params(self, **kwargs: Any) -> None:
        """Optional param validation. Raise ValueError on invalid input."""
        pass
