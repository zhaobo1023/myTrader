# -*- coding: utf-8 -*-
"""
Unit tests for AgentOrchestrator ReAct loop.

Uses mock LLM client and in-memory SQLite.
"""
import os
import sys
import asyncio
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')

from api.services.agent.schemas import ToolDef, AgentContext


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _collect_events(async_gen) -> list[dict]:
    events = []
    async for event in async_gen:
        events.append(event)
    return events


async def _setup_db():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import event, Integer
    from api.dependencies import Base
    from api.models.agent import AgentConversation, AgentMessage  # noqa: F401
    from api.models.user import User  # noqa: F401

    engine = create_async_engine('sqlite+aiosqlite://', echo=False)

    @event.listens_for(engine.sync_engine, 'connect')
    def _enable_fk(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, sf


async def _create_user(session):
    from api.models.user import User, UserTier, UserRole
    user = User(
        username='testuser', hashed_password='fakehash',
        tier=UserTier.FREE, role=UserRole.USER,
    )
    session.add(user)
    await session.flush()
    return user


def _make_registry():
    """Create a fresh ToolRegistry with a mock tool."""
    from api.services.agent.tool_registry import ToolRegistry

    reg = ToolRegistry()

    async def mock_query_portfolio(params, ctx):
        return {"stocks": [{"code": "002594", "name": "BYD"}], "total": 1}

    reg.register(ToolDef(
        name="query_portfolio",
        description="Query portfolio",
        parameters={"type": "object", "properties": {}, "required": []},
        source="builtin",
        handler=mock_query_portfolio,
        category="data",
    ))

    async def mock_add_watchlist(params, ctx):
        return {"success": True}

    reg.register(ToolDef(
        name="add_watchlist",
        description="Add to watchlist",
        parameters={"type": "object", "properties": {
            "stock_code": {"type": "string"},
            "stock_name": {"type": "string"},
        }, "required": ["stock_code", "stock_name"]},
        source="builtin",
        handler=mock_add_watchlist,
        category="action",
    ))

    return reg


class MockLLMClient:
    """Mock LLM client that returns predetermined responses."""

    def __init__(self, responses: list[list[dict]]):
        """responses: list of event sequences, one per LLM call."""
        self._responses = list(responses)
        self._call_idx = 0

    async def chat_stream(self, messages, tools=None, temperature=0.7):
        if self._call_idx >= len(self._responses):
            yield {"type": "token", "content": "Fallback response"}
            yield {"type": "finish", "reason": "stop"}
            return

        events = self._responses[self._call_idx]
        self._call_idx += 1
        for evt in events:
            yield evt


class TestOrchestratorSimpleChat(unittest.TestCase):
    """Test simple text response (no tool calls)."""

    def test_direct_answer(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                from api.services.agent.orchestrator import AgentOrchestrator

                store = ConversationStore(session)
                registry = _make_registry()
                llm = MockLLMClient([
                    [
                        {"type": "token", "content": "Hello"},
                        {"type": "token", "content": " world"},
                        {"type": "finish", "reason": "stop"},
                    ]
                ])

                orch = AgentOrchestrator(registry, llm, store)
                events = await _collect_events(orch.chat(
                    message="Hi",
                    user=user,
                    db=session,
                    redis=MagicMock(),
                ))

                types = [e["type"] for e in events]
                self.assertIn("thinking", types)
                self.assertIn("token", types)
                self.assertIn("done", types)

                # Check content
                tokens = [e["content"] for e in events if e["type"] == "token"]
                self.assertEqual("".join(tokens), "Hello world")

                await session.commit()
            await engine.dispose()

        _run(_test())


class TestOrchestratorToolCall(unittest.TestCase):
    """Test tool call flow."""

    def test_single_tool_call(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                from api.services.agent.orchestrator import AgentOrchestrator

                store = ConversationStore(session)
                registry = _make_registry()
                llm = MockLLMClient([
                    # First call: LLM decides to call tool
                    [
                        {"type": "tool_calls", "calls": [
                            {"id": "call_1", "name": "query_portfolio", "arguments": {}}
                        ]},
                        {"type": "finish", "reason": "tool_calls"},
                    ],
                    # Second call: LLM generates final answer
                    [
                        {"type": "token", "content": "Your portfolio has BYD."},
                        {"type": "finish", "reason": "stop"},
                    ],
                ])

                orch = AgentOrchestrator(registry, llm, store)
                events = await _collect_events(orch.chat(
                    message="What's in my portfolio?",
                    user=user,
                    db=session,
                    redis=MagicMock(),
                ))

                types = [e["type"] for e in events]
                self.assertIn("tool_call", types)
                self.assertIn("tool_result", types)
                self.assertIn("token", types)
                self.assertIn("done", types)

                # Check tool_result
                tool_results = [e for e in events if e["type"] == "tool_result"]
                self.assertEqual(len(tool_results), 1)
                self.assertEqual(tool_results[0]["name"], "query_portfolio")
                self.assertTrue(tool_results[0]["success"])

                await session.commit()
            await engine.dispose()

        _run(_test())

    def test_max_iterations_limit(self):
        """Test that the loop stops after MAX_ITERATIONS."""
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                from api.services.agent.orchestrator import AgentOrchestrator

                store = ConversationStore(session)
                registry = _make_registry()

                # LLM always calls tools
                loop_response = [
                    {"type": "tool_calls", "calls": [
                        {"id": "call_loop", "name": "query_portfolio", "arguments": {}}
                    ]},
                    {"type": "finish", "reason": "tool_calls"},
                ]
                llm = MockLLMClient([loop_response] * 15)

                orch = AgentOrchestrator(registry, llm, store)
                events = await _collect_events(orch.chat(
                    message="Keep calling tools",
                    user=user,
                    db=session,
                    redis=MagicMock(),
                ))

                thinking_events = [e for e in events if e["type"] == "thinking"]
                # Should not exceed MAX_ITERATIONS (10)
                self.assertLessEqual(len(thinking_events), 10)

                await session.commit()
            await engine.dispose()

        _run(_test())


class TestOrchestratorToolFailure(unittest.TestCase):
    """Test tool execution failure handling."""

    def test_tool_error_continues(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                from api.services.agent.orchestrator import AgentOrchestrator
                from api.services.agent.tool_registry import ToolRegistry

                store = ConversationStore(session)
                registry = ToolRegistry()

                async def failing_tool(params, ctx):
                    raise RuntimeError("DB connection failed")

                registry.register(ToolDef(
                    name="failing_tool",
                    description="A tool that always fails",
                    parameters={"type": "object", "properties": {}, "required": []},
                    source="builtin",
                    handler=failing_tool,
                ))

                llm = MockLLMClient([
                    [
                        {"type": "tool_calls", "calls": [
                            {"id": "call_fail", "name": "failing_tool", "arguments": {}}
                        ]},
                        {"type": "finish", "reason": "tool_calls"},
                    ],
                    [
                        {"type": "token", "content": "Sorry, the tool failed."},
                        {"type": "finish", "reason": "stop"},
                    ],
                ])

                orch = AgentOrchestrator(registry, llm, store)
                events = await _collect_events(orch.chat(
                    message="Use the tool",
                    user=user,
                    db=session,
                    redis=MagicMock(),
                ))

                tool_results = [e for e in events if e["type"] == "tool_result"]
                self.assertEqual(len(tool_results), 1)
                self.assertFalse(tool_results[0]["success"])

                # Should still get a final answer
                types = [e["type"] for e in events]
                self.assertIn("done", types)

                await session.commit()
            await engine.dispose()

        _run(_test())


class TestActionEvents(unittest.TestCase):
    """Test action tool produces action events."""

    def test_action_tool_emits_action_event(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                from api.services.agent.orchestrator import AgentOrchestrator

                store = ConversationStore(session)
                registry = _make_registry()
                llm = MockLLMClient([
                    [
                        {"type": "tool_calls", "calls": [
                            {"id": "call_action", "name": "add_watchlist",
                             "arguments": {"stock_code": "002594", "stock_name": "BYD"}}
                        ]},
                        {"type": "finish", "reason": "tool_calls"},
                    ],
                    [
                        {"type": "token", "content": "Added to watchlist."},
                        {"type": "finish", "reason": "stop"},
                    ],
                ])

                orch = AgentOrchestrator(registry, llm, store)
                events = await _collect_events(orch.chat(
                    message="Watch BYD for me",
                    user=user,
                    db=session,
                    redis=MagicMock(),
                ))

                action_events = [e for e in events if e["type"] == "action"]
                self.assertEqual(len(action_events), 1)
                self.assertEqual(action_events[0]["action"], "add_watchlist")
                self.assertEqual(action_events[0]["payload"]["stock_code"], "002594")

                await session.commit()
            await engine.dispose()

        _run(_test())


class TestOrchestratorConversationPersistence(unittest.TestCase):
    """Test that messages are saved to the store."""

    def test_messages_saved(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                from api.services.agent.orchestrator import AgentOrchestrator

                store = ConversationStore(session)
                registry = _make_registry()
                llm = MockLLMClient([
                    [
                        {"type": "token", "content": "Answer"},
                        {"type": "finish", "reason": "stop"},
                    ]
                ])

                orch = AgentOrchestrator(registry, llm, store)
                events = await _collect_events(orch.chat(
                    message="Test save",
                    user=user,
                    db=session,
                    redis=MagicMock(),
                ))

                # Get conversation ID from done event
                done_events = [e for e in events if e["type"] == "done"]
                self.assertEqual(len(done_events), 1)
                conv_id = done_events[0]["conversation_id"]

                # Check messages were saved
                msgs = await store.get_messages(conv_id)
                roles = [m["role"] for m in msgs]
                self.assertIn("user", roles)
                self.assertIn("assistant", roles)

                await session.commit()
            await engine.dispose()

        _run(_test())


if __name__ == '__main__':
    unittest.main()
