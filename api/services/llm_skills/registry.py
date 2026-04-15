# -*- coding: utf-8 -*-
"""
LLM Skill registry.

Usage:
    @register
    class MySkill(LLMSkillBase):
        ...

    skill = get_skill("my-skill-id")
    if skill:
        async for event in skill.stream(...):
            ...
"""
from typing import Type
from api.services.llm_skills.base import LLMSkillBase

_REGISTRY: dict[str, Type[LLMSkillBase]] = {}


def register(skill_cls: Type[LLMSkillBase]) -> Type[LLMSkillBase]:
    """Decorator: register a LLM Skill class by its skill_id."""
    meta = skill_cls().meta
    _REGISTRY[meta.skill_id] = skill_cls
    return skill_cls


def get_skill(skill_id: str) -> LLMSkillBase | None:
    cls = _REGISTRY.get(skill_id)
    return cls() if cls else None


def list_skills() -> list[dict]:
    return [
        {
            'skill_id': cls().meta.skill_id,
            'name': cls().meta.name,
            'version': cls().meta.version,
            'description': cls().meta.description,
            'min_tier': cls().meta.min_tier,
        }
        for cls in _REGISTRY.values()
    ]
