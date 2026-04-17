# -*- coding: utf-8 -*-
"""
Integration test fixtures -- in-memory SQLite async database + httpx AsyncClient.

Provides a real FastAPI app with all routers, backed by a fresh SQLite DB
for each test function. No mocking -- full end-to-end through the stack.
"""
import os
import sys
import asyncio
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# Must be set before importing api modules
os.environ.setdefault('JWT_SECRET_KEY', 'test-secret-key-for-integration')
os.environ.setdefault('REDIS_HOST', 'localhost')
os.environ.setdefault('API_DEBUG', 'false')


@pytest.fixture(scope='session')
def event_loop():
    """Use a single event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Create a fresh in-memory SQLite async engine per test."""
    engine = create_async_engine(
        'sqlite+aiosqlite://',
        echo=False,
    )
    # Enable FK enforcement for SQLite
    @event.listens_for(engine.sync_engine, 'connect')
    def _enable_fk(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

    # Import all models so Base.metadata is populated
    from api.models import (  # noqa: F401
        User, Subscription, UsageLog, ApiKey, Strategy, BacktestJob,
        UserWatchlist, UserScanResult, UserNotificationConfig,
        InviteCode, UserPosition, InboxMessage,
    )
    from api.dependencies import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Yield an async session bound to the test engine."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    """Yield an httpx AsyncClient wired to the FastAPI app with overridden DB."""
    from api.dependencies import get_db, Base

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False,
    )

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    from api.main import app
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

async def create_admin_user(db_session: AsyncSession) -> 'User':
    """Insert an admin user and return it."""
    from api.models.user import User, UserTier, UserRole
    from api.core.security import hash_password
    admin = User(
        username='admin',
        display_name='Admin',
        hashed_password=hash_password('admin123'),
        tier=UserTier.FREE,
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


async def create_invite_code(db_session: AsyncSession, admin_id: int, code: str = 'TESTCODE') -> 'InviteCode':
    """Insert an invite code."""
    from api.models.invite_code import InviteCode
    invite = InviteCode(
        code=code,
        created_by=admin_id,
        max_uses=1,
        use_count=0,
        is_active=True,
    )
    db_session.add(invite)
    await db_session.commit()
    await db_session.refresh(invite)
    return invite


async def register_user(client: AsyncClient, username: str, password: str, invite_code: str) -> dict:
    """Register a user via the API and return the response JSON."""
    resp = await client.post('/api/auth/register', json={
        'username': username,
        'password': password,
        'invite_code': invite_code,
    })
    assert resp.status_code == 201, f'Register failed: {resp.text}'
    return resp.json()


async def login_user(client: AsyncClient, username: str, password: str) -> str:
    """Login and return the access token."""
    resp = await client.post('/api/auth/login', json={
        'username': username,
        'password': password,
    })
    assert resp.status_code == 200, f'Login failed: {resp.text}'
    return resp.json()['access_token']


def auth_headers(token: str) -> dict:
    """Build Authorization headers."""
    return {'Authorization': f'Bearer {token}'}
