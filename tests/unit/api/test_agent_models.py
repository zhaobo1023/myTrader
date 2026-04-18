# -*- coding: utf-8 -*-
"""
Unit tests for Agent ORM models: AgentConversation, AgentMessage.
"""
import os
import sys
import asyncio
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')


class TestAgentConversationModel(unittest.TestCase):
    """Tests for AgentConversation ORM model."""

    def test_table_name(self):
        from api.models.agent import AgentConversation
        self.assertEqual(AgentConversation.__tablename__, 'agent_conversations')

    def test_columns_exist(self):
        from api.models.agent import AgentConversation
        cols = {c.name for c in AgentConversation.__table__.columns}
        expected = {'id', 'user_id', 'title', 'active_skill', 'created_at', 'updated_at'}
        self.assertTrue(expected.issubset(cols), f"Missing columns: {expected - cols}")

    def test_id_is_string_pk(self):
        from api.models.agent import AgentConversation
        id_col = AgentConversation.__table__.c.id
        self.assertTrue(id_col.primary_key)

    def test_repr(self):
        from api.models.agent import AgentConversation
        conv = AgentConversation(id='abc', user_id=1)
        self.assertIn('abc', repr(conv))


class TestAgentMessageModel(unittest.TestCase):
    """Tests for AgentMessage ORM model."""

    def test_table_name(self):
        from api.models.agent import AgentMessage
        self.assertEqual(AgentMessage.__tablename__, 'agent_messages')

    def test_columns_exist(self):
        from api.models.agent import AgentMessage
        cols = {c.name for c in AgentMessage.__table__.columns}
        expected = {
            'id', 'conversation_id', 'role', 'content',
            'tool_calls', 'tool_call_id', 'tool_name', 'metadata_json', 'created_at',
        }
        self.assertTrue(expected.issubset(cols), f"Missing columns: {expected - cols}")

    def test_to_llm_dict_user(self):
        from api.models.agent import AgentMessage
        msg = AgentMessage(role='user', content='hello')
        d = msg.to_llm_dict()
        self.assertEqual(d['role'], 'user')
        self.assertEqual(d['content'], 'hello')
        self.assertNotIn('tool_call_id', d)

    def test_to_llm_dict_assistant_with_tool_calls(self):
        from api.models.agent import AgentMessage
        calls = [{"id": "c1", "function": {"name": "test", "arguments": "{}"}}]
        msg = AgentMessage(role='assistant', content='', tool_calls=calls)
        d = msg.to_llm_dict()
        self.assertEqual(d['role'], 'assistant')
        self.assertEqual(d['tool_calls'], calls)

    def test_to_llm_dict_tool(self):
        from api.models.agent import AgentMessage
        msg = AgentMessage(role='tool', content='{"ok": true}', tool_call_id='c1', tool_name='test_tool')
        d = msg.to_llm_dict()
        self.assertEqual(d['role'], 'tool')
        self.assertEqual(d['tool_call_id'], 'c1')
        self.assertEqual(d['name'], 'test_tool')

    def test_repr(self):
        from api.models.agent import AgentMessage
        msg = AgentMessage(id=42, role='user')
        self.assertIn('42', repr(msg))


if __name__ == '__main__':
    unittest.main()
