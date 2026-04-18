# -*- coding: utf-8 -*-
"""
Unit tests for Plugin system: YAML parser, PluginLoader, investment master plugins.
"""
import os
import sys
import asyncio
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')

PLUGINS_DIR = os.path.join(ROOT, 'plugins')


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestYAMLParser(unittest.TestCase):
    """T22: Test parse_skill_yaml function."""

    def test_parse_prompt_skill(self):
        from api.services.agent.plugin_loader import parse_skill_yaml
        path = os.path.join(PLUGINS_DIR, 'masters', 'buffett', 'skill.yaml')
        skill = parse_skill_yaml(path)
        self.assertEqual(skill.name, 'buffett_analysis')
        self.assertEqual(skill.type, 'prompt_skill')
        self.assertIsNotNone(skill.system_prompt)
        self.assertTrue(len(skill.system_prompt) > 100)
        self.assertTrue(skill.is_prompt_skill)
        self.assertFalse(skill.is_code_skill)

    def test_parse_code_skill(self):
        from api.services.agent.plugin_loader import parse_skill_yaml
        # Create a temp code_skill yaml
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: test_code
display_name: "Test Code Skill"
description: "A test code skill"
version: "1.0.0"
author: "test"
type: "code_skill"
entry_point: "plugins.community._example.handler.run"
parameters:
  type: object
  properties:
    top_n:
      type: integer
      default: 10
  required: []
""")
            f.flush()
            skill = parse_skill_yaml(f.name)
            self.assertEqual(skill.type, 'code_skill')
            self.assertEqual(skill.entry_point, 'plugins.community._example.handler.run')
            self.assertTrue(skill.is_code_skill)
            os.unlink(f.name)

    def test_missing_required_field(self):
        from api.services.agent.plugin_loader import parse_skill_yaml
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("name: incomplete\n")
            f.flush()
            with self.assertRaises(ValueError):
                parse_skill_yaml(f.name)
            os.unlink(f.name)

    def test_invalid_type(self):
        from api.services.agent.plugin_loader import parse_skill_yaml
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: bad
display_name: "Bad"
description: "bad type"
version: "1.0.0"
author: "test"
type: "invalid_type"
""")
            f.flush()
            with self.assertRaises(ValueError):
                parse_skill_yaml(f.name)
            os.unlink(f.name)

    def test_prompt_skill_without_system_prompt(self):
        from api.services.agent.plugin_loader import parse_skill_yaml
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: no_prompt
display_name: "No prompt"
description: "missing system_prompt"
version: "1.0.0"
author: "test"
type: "prompt_skill"
""")
            f.flush()
            with self.assertRaises(ValueError):
                parse_skill_yaml(f.name)
            os.unlink(f.name)

    def test_empty_file(self):
        from api.services.agent.plugin_loader import parse_skill_yaml
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            f.flush()
            with self.assertRaises(ValueError):
                parse_skill_yaml(f.name)
            os.unlink(f.name)


class TestPluginLoader(unittest.TestCase):
    """T23: Test PluginLoader class."""

    def test_load_all_finds_plugins(self):
        from api.services.agent.plugin_loader import PluginLoader
        loader = PluginLoader(PLUGINS_DIR)
        tools = loader.load_all()
        self.assertGreaterEqual(len(tools), 5)  # 5 masters

    def test_prompt_skill_becomes_tooldef(self):
        from api.services.agent.plugin_loader import PluginLoader
        loader = PluginLoader(PLUGINS_DIR)
        tools = loader.load_all()
        buffett = None
        for t in tools:
            if t.name == 'buffett_analysis':
                buffett = t
                break
        self.assertIsNotNone(buffett)
        self.assertEqual(buffett.source, 'plugin')
        self.assertEqual(buffett.category, 'analysis')
        self.assertTrue(hasattr(buffett, '_plugin_system_prompt'))

    def test_prompt_skill_handler_returns_activation(self):
        from api.services.agent.plugin_loader import PluginLoader
        from unittest.mock import MagicMock
        loader = PluginLoader(PLUGINS_DIR)
        tools = loader.load_all()
        buffett = [t for t in tools if t.name == 'buffett_analysis'][0]
        result = _run(buffett.handler({}, MagicMock()))
        self.assertEqual(result["type"], "skill_activated")
        self.assertIn("system_prompt", result)

    def test_nonexistent_dir_returns_empty(self):
        from api.services.agent.plugin_loader import PluginLoader
        loader = PluginLoader('/nonexistent/path')
        tools = loader.load_all()
        self.assertEqual(tools, [])

    def test_get_skill_def(self):
        from api.services.agent.plugin_loader import PluginLoader
        loader = PluginLoader(PLUGINS_DIR)
        loader.load_all()
        skill = loader.get_skill_def('buffett_analysis')
        self.assertIsNotNone(skill)
        self.assertEqual(skill.display_name, '巴菲特价值投资分析')

    def test_get_all_skill_defs(self):
        from api.services.agent.plugin_loader import PluginLoader
        loader = PluginLoader(PLUGINS_DIR)
        loader.load_all()
        all_skills = loader.get_all_skill_defs()
        self.assertGreaterEqual(len(all_skills), 5)


class TestMasterPlugins(unittest.TestCase):
    """T24-T25: Test investment master YAML plugins."""

    def _parse(self, master_name):
        from api.services.agent.plugin_loader import parse_skill_yaml
        path = os.path.join(PLUGINS_DIR, 'masters', master_name, 'skill.yaml')
        return parse_skill_yaml(path)

    def test_buffett_yaml(self):
        skill = self._parse('buffett')
        self.assertEqual(skill.name, 'buffett_analysis')
        self.assertIn('护城河', skill.system_prompt)
        self.assertIn('query_database', skill.required_tools)

    def test_graham_yaml(self):
        skill = self._parse('graham')
        self.assertEqual(skill.name, 'graham_analysis')
        self.assertIn('安全边际', skill.system_prompt)
        self.assertIn('query_database', skill.required_tools)

    def test_peter_lynch_yaml(self):
        skill = self._parse('peter_lynch')
        self.assertEqual(skill.name, 'peter_lynch_analysis')
        self.assertIn('PEG', skill.system_prompt)

    def test_livermore_yaml(self):
        skill = self._parse('livermore')
        self.assertEqual(skill.name, 'livermore_analysis')
        self.assertIn('趋势', skill.system_prompt)
        self.assertIn('get_stock_indicators', skill.required_tools)

    def test_munger_yaml(self):
        skill = self._parse('munger')
        self.assertEqual(skill.name, 'munger_analysis')
        self.assertIn('逆向思考', skill.system_prompt)

    def test_all_masters_have_reasonable_prompt_length(self):
        masters = ['buffett', 'graham', 'peter_lynch', 'livermore', 'munger']
        for m in masters:
            skill = self._parse(m)
            self.assertGreater(
                len(skill.system_prompt), 200,
                f"{m} system_prompt too short: {len(skill.system_prompt)} chars"
            )
            self.assertLess(
                len(skill.system_prompt), 3000,
                f"{m} system_prompt too long: {len(skill.system_prompt)} chars"
            )


if __name__ == '__main__':
    unittest.main()
