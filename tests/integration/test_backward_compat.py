# -*- coding: utf-8 -*-
"""
P4-T4: Backward compatibility.

- Public routes (health, market_overview, theme_pool, candidate_pool) work without auth
- Root endpoint works
- Protected endpoints return 401 without token
"""
import pytest

from tests.integration.conftest import (
    create_admin_user, create_invite_code, register_user, auth_headers,
)

pytestmark = pytest.mark.asyncio


async def test_health_no_auth(client, db_session):
    """GET /health is accessible without authentication."""
    resp = await client.get('/health')
    assert resp.status_code == 200


async def test_root_no_auth(client, db_session):
    """GET / is accessible without authentication."""
    resp = await client.get('/')
    assert resp.status_code == 200
    data = resp.json()
    assert 'name' in data
    assert 'version' in data


async def test_docs_no_auth(client, db_session):
    """GET /docs is accessible without authentication."""
    resp = await client.get('/docs')
    assert resp.status_code == 200


async def test_protected_positions_requires_auth(client, db_session):
    """Positions endpoints require auth."""
    # List
    resp = await client.get('/api/positions')
    assert resp.status_code in (401, 403)

    # Create
    resp = await client.post('/api/positions', json={
        'stock_code': '000001', 'stock_name': 'Test',
    })
    assert resp.status_code in (401, 403)


async def test_protected_inbox_requires_auth(client, db_session):
    """Inbox endpoints require auth."""
    resp = await client.get('/api/inbox')
    assert resp.status_code in (401, 403)

    resp = await client.get('/api/inbox/unread-count')
    assert resp.status_code in (401, 403)


async def test_protected_watchlist_requires_auth(client, db_session):
    """Watchlist endpoints require auth."""
    resp = await client.get('/api/watchlist')
    assert resp.status_code in (401, 403)


async def test_protected_auth_me_requires_auth(client, db_session):
    """GET /api/auth/me requires auth."""
    resp = await client.get('/api/auth/me')
    assert resp.status_code in (401, 403)


async def test_admin_endpoints_require_admin_role(client, db_session):
    """Admin endpoints reject regular users with 403."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='COMPAT1')
    reg = await register_user(client, 'regular', 'pass1234', 'COMPAT1')
    token = reg['access_token']

    # Regular user hits admin invite-code endpoint
    resp = await client.get('/api/admin/invite-codes', headers=auth_headers(token))
    assert resp.status_code == 403


async def test_admin_endpoints_work_for_admin(client, db_session):
    """Admin can access admin endpoints."""
    from api.core.security import create_access_token
    admin = await create_admin_user(db_session)

    token_data = {'sub': str(admin.id), 'username': 'admin', 'tier': 'free'}
    token = create_access_token(token_data)

    # Admin can list invite codes
    resp = await client.get('/api/admin/invite-codes', headers=auth_headers(token))
    assert resp.status_code == 200

    # Admin can generate invite codes
    resp = await client.post('/api/admin/invite-codes', headers=auth_headers(token), json={
        'count': 3, 'max_uses': 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3


async def test_register_login_public(client, db_session):
    """Register and login endpoints are accessible without pre-existing auth."""
    # Login with non-existent user
    resp = await client.post('/api/auth/login', json={
        'username': 'nobody', 'password': 'whatever',
    })
    assert resp.status_code == 401  # Not 403 or 500

    # Register without invite code
    resp = await client.post('/api/auth/register', json={
        'username': 'someone', 'password': 'pass1234', 'invite_code': 'FAKE',
    })
    assert resp.status_code == 400  # Not 403 or 500
