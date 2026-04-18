# -*- coding: utf-8 -*-
"""
Plugin system - load YAML-defined skills as agent tools.

Two plugin types:
  - prompt_skill: pure YAML with system_prompt (no code needed)
  - code_skill: YAML + Python handler (needs entry_point)
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

from api.services.agent.schemas import ToolDef

logger = logging.getLogger('myTrader.agent.plugins')

VALID_TYPES = ("prompt_skill", "code_skill")


@dataclass
class PluginSkillDef:
    """Parsed plugin skill definition from skill.yaml."""
    name: str
    display_name: str
    description: str
    version: str
    author: str
    min_tier: str = "free"
    type: str = "prompt_skill"
    system_prompt: Optional[str] = None
    required_tools: list[str] = field(default_factory=list)
    entry_point: Optional[str] = None
    parameters: Optional[dict] = None

    @property
    def is_prompt_skill(self) -> bool:
        return self.type == "prompt_skill"

    @property
    def is_code_skill(self) -> bool:
        return self.type == "code_skill"


def parse_skill_yaml(path: str) -> PluginSkillDef:
    """Parse a single skill.yaml file into a PluginSkillDef.

    Raises ValueError on invalid format.
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid skill.yaml: expected dict, got {type(data)}")

    # Required fields
    for field_name in ('name', 'display_name', 'description', 'version', 'author', 'type'):
        if field_name not in data:
            raise ValueError(f"Missing required field '{field_name}' in {path}")

    skill_type = data['type']
    if skill_type not in VALID_TYPES:
        raise ValueError(f"Invalid type '{skill_type}' in {path}. Must be one of {VALID_TYPES}")

    if skill_type == "prompt_skill" and not data.get("system_prompt"):
        raise ValueError(f"prompt_skill requires 'system_prompt' in {path}")

    if skill_type == "code_skill" and not data.get("entry_point"):
        raise ValueError(f"code_skill requires 'entry_point' in {path}")

    return PluginSkillDef(
        name=data['name'],
        display_name=data['display_name'],
        description=data['description'],
        version=data['version'],
        author=data['author'],
        min_tier=data.get('min_tier', 'free'),
        type=skill_type,
        system_prompt=data.get('system_prompt'),
        required_tools=data.get('required_tools', []),
        entry_point=data.get('entry_point'),
        parameters=data.get('parameters'),
    )


class PluginLoader:
    """Scan plugins/ directory and load all skills as ToolDefs."""

    def __init__(self, plugins_dir: str):
        self.plugins_dir = plugins_dir
        self._skills: dict[str, PluginSkillDef] = {}

    def load_all(self) -> list[ToolDef]:
        """Scan for skill.yaml files and load all plugins."""
        if not os.path.isdir(self.plugins_dir):
            logger.warning('[PluginLoader] plugins dir not found: %s', self.plugins_dir)
            return []

        tool_defs = []
        for root, dirs, files in os.walk(self.plugins_dir):
            if 'skill.yaml' in files:
                yaml_path = os.path.join(root, 'skill.yaml')
                try:
                    skill_def = parse_skill_yaml(yaml_path)
                    tool_def = self._load_plugin(skill_def)
                    self._skills[skill_def.name] = skill_def
                    tool_defs.append(tool_def)
                    logger.info('[PluginLoader] loaded plugin: %s (%s)', skill_def.name, skill_def.type)
                except Exception as e:
                    logger.error('[PluginLoader] failed to load %s: %s', yaml_path, e)
                    continue

        return tool_defs

    def _load_plugin(self, skill_def: PluginSkillDef) -> ToolDef:
        """Convert a PluginSkillDef to a ToolDef."""
        if skill_def.is_prompt_skill:
            return self._load_prompt_skill(skill_def)
        else:
            return self._load_code_skill(skill_def)

    def _load_prompt_skill(self, skill_def: PluginSkillDef) -> ToolDef:
        """Create a ToolDef for a prompt_skill.

        The handler returns a special response that tells the orchestrator
        to activate this skill's system_prompt.
        """
        system_prompt = skill_def.system_prompt
        required_tools = skill_def.required_tools

        async def handler(params: dict, ctx) -> dict:
            return {
                "type": "skill_activated",
                "skill_name": skill_def.name,
                "display_name": skill_def.display_name,
                "system_prompt": system_prompt,
                "required_tools": required_tools,
            }

        tool_def = ToolDef(
            name=skill_def.name,
            description=skill_def.description,
            parameters={"type": "object", "properties": {}, "required": []},
            source="plugin",
            handler=handler,
            requires_tier=skill_def.min_tier,
            category="analysis",
        )
        # Attach system_prompt for orchestrator to use
        tool_def._plugin_system_prompt = system_prompt
        return tool_def

    def _load_code_skill(self, skill_def: PluginSkillDef) -> ToolDef:
        """Load a code_skill by dynamically importing its entry_point."""
        module_path, func_name = skill_def.entry_point.rsplit('.', 1)
        module = importlib.import_module(module_path)
        handler = getattr(module, func_name)

        return ToolDef(
            name=skill_def.name,
            description=skill_def.description,
            parameters=skill_def.parameters or {"type": "object", "properties": {}, "required": []},
            source="plugin",
            handler=handler,
            requires_tier=skill_def.min_tier,
            category="analysis",
        )

    def get_skill_def(self, name: str) -> Optional[PluginSkillDef]:
        """Get the original PluginSkillDef by name."""
        return self._skills.get(name)

    def get_all_skill_defs(self) -> list[PluginSkillDef]:
        """Return all loaded skill definitions."""
        return list(self._skills.values())
