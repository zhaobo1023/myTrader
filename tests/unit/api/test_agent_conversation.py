# -*- coding: utf-8 -*-
"""
Unit tests for ConversationStore.

Uses in-memory SQLite async engine for DB operations.
"""
import os
import sys
import asyncio
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

os.environ.setdefault('JWT_SECRET_KEY', 'test-secret')
os.environ.setdefault('REDIS_HOST', 'localhost')


def _run(coro):
    """Helper to run async code in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _setup_db():
    """Create in-memory SQLite engine with agent tables."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import event
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

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def _create_user(session):
    """Insert a minimal user for FK constraints."""
    from api.models.user import User, UserTier, UserRole
    user = User(
        username='testuser',
        hashed_password='fakehash',
        tier=UserTier.FREE,
        role=UserRole.USER,
    )
    session.add(user)
    await session.flush()
    return user


class TestConversationStore(unittest.TestCase):
    """Tests for ConversationStore."""

    def test_create_returns_uuid(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                self.assertIsNotNone(conv_id)
                self.assertEqual(len(conv_id), 36)  # UUID format
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_create_with_title(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id, title="Test conversation")
                conv = await store.get_conversation(conv_id)
                self.assertEqual(conv.title, "Test conversation")
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_save_and_get_messages(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                await store.save_message(conv_id, "user", "hello")
                await store.save_message(conv_id, "assistant", "hi there")
                msgs = await store.get_messages(conv_id)
                self.assertEqual(len(msgs), 2)
                self.assertEqual(msgs[0]["role"], "user")
                self.assertEqual(msgs[1]["role"], "assistant")
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_get_messages_limit(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                for i in range(10):
                    await store.save_message(conv_id, "user", f"msg {i}")
                msgs = await store.get_messages(conv_id, limit=3)
                self.assertEqual(len(msgs), 3)
                # Should be last 3 messages
                self.assertEqual(msgs[0]["content"], "msg 7")
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_get_messages_for_llm(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                await store.save_message(conv_id, "user", "test query")
                await store.save_message(conv_id, "assistant", "test answer")
                llm_msgs = await store.get_messages_for_llm(conv_id)
                self.assertEqual(len(llm_msgs), 2)
                self.assertEqual(llm_msgs[0]["role"], "user")
                self.assertEqual(llm_msgs[0]["content"], "test query")
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_tool_message_includes_call_id(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                await store.save_message(
                    conv_id, "tool", '{"data": 1}',
                    tool_call_id="call_abc", tool_name="query_portfolio",
                )
                msgs = await store.get_messages(conv_id)
                self.assertEqual(msgs[0]["tool_call_id"], "call_abc")
                self.assertEqual(msgs[0]["tool_name"], "query_portfolio")
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_auto_title_from_first_user_message(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                await store.save_message(conv_id, "user", "analyze my portfolio risk")
                conv = await store.get_conversation(conv_id)
                self.assertEqual(conv.title, "analyze my portfolio risk")
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_delete_conversation(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                await store.save_message(conv_id, "user", "test")
                result = await store.delete_conversation(conv_id, user.id)
                self.assertTrue(result)
                conv = await store.get_conversation(conv_id)
                self.assertIsNone(conv)
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_delete_other_user_conversation_fails(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                conv_id = await store.create(user.id)
                result = await store.delete_conversation(conv_id, user_id=9999)
                self.assertFalse(result)
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_list_conversations(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                await store.create(user.id, "conv 1")
                await store.create(user.id, "conv 2")
                convs = await store.list_conversations(user.id)
                self.assertEqual(len(convs), 2)
                await session.commit()
            await engine.dispose()
        _run(_test())

    def test_list_conversations_only_own(self):
        async def _test():
            engine, sf = await _setup_db()
            async with sf() as session:
                user = await _create_user(session)
                from api.services.agent.conversation import ConversationStore
                store = ConversationStore(session)
                await store.create(user.id, "my conv")
                convs = await store.list_conversations(user_id=9999)
                self.assertEqual(len(convs), 0)
                await session.commit()
            await engine.dispose()
        _run(_test())


if __name__ == '__main__':
    unittest.main()
