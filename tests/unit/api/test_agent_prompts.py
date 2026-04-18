# -*- coding: utf-8 -*-
"""
Unit tests for Agent system prompt builder.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')


class TestAgentSystemPrompt(unittest.TestCase):
    """Tests for AGENT_SYSTEM_PROMPT constant."""

    def test_contains_core_instructions(self):
        from api.services.agent.prompts import AGENT_SYSTEM_PROMPT
        self.assertIn("myTrader", AGENT_SYSTEM_PROMPT)
        self.assertIn("emoji", AGENT_SYSTEM_PROMPT)
        self.assertIn("中文", AGENT_SYSTEM_PROMPT)

    def test_no_emoji_in_prompt(self):
        from api.services.agent.prompts import AGENT_SYSTEM_PROMPT
        # Check no common emoji characters
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF]",
            flags=re.UNICODE,
        )
        self.assertIsNone(emoji_pattern.search(AGENT_SYSTEM_PROMPT))


class TestBuildSystemPrompt(unittest.TestCase):
    """Tests for build_system_prompt function."""

    def test_base_prompt_only(self):
        from api.services.agent.prompts import build_system_prompt, AGENT_SYSTEM_PROMPT
        result = build_system_prompt()
        self.assertIn(AGENT_SYSTEM_PROMPT, result)

    def test_market_page_context(self):
        from api.services.agent.prompts import build_system_prompt
        result = build_system_prompt(page_context={"page": "market"})
        self.assertIn("行情看板", result)

    def test_dashboard_page_context(self):
        from api.services.agent.prompts import build_system_prompt
        result = build_system_prompt(page_context={"page": "dashboard"})
        self.assertIn("持仓", result)

    def test_stock_code_injection(self):
        from api.services.agent.prompts import build_system_prompt
        result = build_system_prompt(
            page_context={"page": "market", "stock_code": "002594", "stock_name": "比亚迪"},
        )
        self.assertIn("002594", result)
        self.assertIn("比亚迪", result)

    def test_active_skill_prompt(self):
        from api.services.agent.prompts import build_system_prompt
        skill_prompt = "你是巴菲特价值投资分析师"
        result = build_system_prompt(active_skill_prompt=skill_prompt)
        self.assertIn(skill_prompt, result)
        self.assertIn("分析框架", result)

    def test_tool_names_list(self):
        from api.services.agent.prompts import build_system_prompt
        result = build_system_prompt(tool_names=["query_portfolio", "get_stock_indicators"])
        self.assertIn("query_portfolio", result)
        self.assertIn("get_stock_indicators", result)

    def test_unknown_page_no_crash(self):
        from api.services.agent.prompts import build_system_prompt
        result = build_system_prompt(page_context={"page": "unknown_page"})
        # Should not crash, just no page hint
        self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
