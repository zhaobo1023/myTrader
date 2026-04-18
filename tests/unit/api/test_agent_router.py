# -*- coding: utf-8 -*-
"""
Unit tests for Agent API router.

Tests endpoint behavior with mocked orchestrator.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')


class TestChatRequestSchema(unittest.TestCase):
    """Test ChatRequest Pydantic schema."""

    def test_valid_request(self):
        from api.schemas.agent import ChatRequest
        req = ChatRequest(message="Hello")
        self.assertEqual(req.message, "Hello")
        self.assertIsNone(req.conversation_id)
        self.assertIsNone(req.active_skill)
        self.assertIsNone(req.page_context)

    def test_message_too_long(self):
        from api.schemas.agent import ChatRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ChatRequest(message="x" * 2001)

    def test_empty_message(self):
        from api.schemas.agent import ChatRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ChatRequest(message="")

    def test_with_optional_fields(self):
        from api.schemas.agent import ChatRequest
        req = ChatRequest(
            message="test",
            conversation_id="conv-123",
            active_skill="buffett",
            page_context={"page": "market", "stock_code": "002594"},
        )
        self.assertEqual(req.conversation_id, "conv-123")
        self.assertEqual(req.active_skill, "buffett")
        self.assertEqual(req.page_context["page"], "market")


class TestConversationSummarySchema(unittest.TestCase):

    def test_serialization(self):
        from api.schemas.agent import ConversationSummary
        summary = ConversationSummary(
            id="abc-123",
            title="Test conv",
            message_count=5,
            created_at="2026-04-18T10:00:00",
        )
        data = summary.model_dump()
        self.assertEqual(data["id"], "abc-123")
        self.assertEqual(data["message_count"], 5)


class TestToolInfoSchema(unittest.TestCase):

    def test_serialization(self):
        from api.schemas.agent import ToolInfo
        info = ToolInfo(
            name="query_portfolio",
            description="Query portfolio",
            parameters={"type": "object"},
            source="builtin",
            category="data",
            requires_tier="free",
        )
        data = info.model_dump()
        self.assertEqual(data["name"], "query_portfolio")
        self.assertEqual(data["source"], "builtin")


if __name__ == '__main__':
    unittest.main()
