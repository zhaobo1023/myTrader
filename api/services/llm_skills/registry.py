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

# Maps skill_id -> (class, SkillMeta).  Meta is captured once at @register time.
_REGISTRY: dict[str, tuple[Type[LLMSkillBase], object]] = {}


def register(skill_cls: Type[LLMSkillBase]) -> Type[LLMSkillBase]:
    """Decorator: register a LLM Skill class by its skill_id.

    Creates one throw-away instance only to read the meta dataclass, then
    discards it.  This keeps the import-time cost minimal and avoids repeated
    instantiation in list_skills / get_skill.
    """
    meta = skill_cls().meta
    _REGISTRY[meta.skill_id] = (skill_cls, meta)
    return skill_cls


def get_skill(skill_id: str) -> LLMSkillBase | None:
    """Return a fresh skill instance, or None if the skill_id is unknown."""
    entry = _REGISTRY.get(skill_id)
    return entry[0]() if entry else None


def list_skills() -> list[dict]:
    return [
        {
            'skill_id': meta.skill_id,
            'name': meta.name,
            'version': meta.version,
            'description': meta.description,
            'min_tier': meta.min_tier,
        }
        for _, meta in _REGISTRY.values()
    ]
