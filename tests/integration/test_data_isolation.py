# -*- coding: utf-8 -*-
"""
P4-T2: Multi-tenant data isolation.

Create two users. Each creates positions, watchlist items, and inbox messages.
Verify that user A cannot see or modify user B's data via any API.
"""
import pytest

from tests.integration.conftest import (
    create_admin_user, create_invite_code, register_user, auth_headers,
)

pytestmark = pytest.mark.asyncio


async def _setup_two_users(client, db_session):
    """Create admin + two regular users, return (token_a, token_b)."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='ISO_A')
    await create_invite_code(db_session, admin.id, code='ISO_B')
    reg_a = await register_user(client, 'user_a', 'pass1234', 'ISO_A')
    reg_b = await register_user(client, 'user_b', 'pass1234', 'ISO_B')
    return reg_a['access_token'], reg_b['access_token']


# ------------------------------------------------------------------
# Positions isolation
# ------------------------------------------------------------------

async def test_positions_isolation(client, db_session):
    """User A's positions are invisible to user B."""
    token_a, token_b = await _setup_two_users(client, db_session)

    # A creates a position
    resp = await client.post('/api/positions', headers=auth_headers(token_a), json={
        'stock_code': '000001', 'stock_name': 'TestA', 'level': 'L1', 'shares': 1000,
    })
    assert resp.status_code == 201
    pos_id = resp.json()['id']

    # B creates a different position
    resp = await client.post('/api/positions', headers=auth_headers(token_b), json={
        'stock_code': '600036', 'stock_name': 'TestB', 'level': 'L2', 'shares': 500,
    })
    assert resp.status_code == 201

    # A lists positions -- only sees their own
    resp = await client.get('/api/positions', headers=auth_headers(token_a))
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['stock_code'] == '000001'

    # B lists positions -- only sees their own
    resp = await client.get('/api/positions', headers=auth_headers(token_b))
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['stock_code'] == '600036'

    # B tries to update A's position -> 404
    resp = await client.put(f'/api/positions/{pos_id}', headers=auth_headers(token_b), json={
        'stock_name': 'Hacked',
    })
    assert resp.status_code == 404

    # B tries to delete A's position -> 404
    resp = await client.delete(f'/api/positions/{pos_id}', headers=auth_headers(token_b))
    assert resp.status_code == 404


async def test_positions_same_stock_different_users(client, db_session):
    """Two users can hold the same stock without conflict."""
    token_a, token_b = await _setup_two_users(client, db_session)

    resp = await client.post('/api/positions', headers=auth_headers(token_a), json={
        'stock_code': '000001', 'stock_name': 'PingAn', 'level': 'L1',
    })
    assert resp.status_code == 201

    resp = await client.post('/api/positions', headers=auth_headers(token_b), json={
        'stock_code': '000001', 'stock_name': 'PingAn', 'level': 'L2',
    })
    assert resp.status_code == 201


# ------------------------------------------------------------------
# Watchlist isolation
# ------------------------------------------------------------------

async def test_watchlist_isolation(client, db_session):
    """User A's watchlist is invisible to user B."""
    token_a, token_b = await _setup_two_users(client, db_session)

    # A adds to watchlist
    resp = await client.post('/api/watchlist', headers=auth_headers(token_a), json={
        'stock_code': '000858', 'stock_name': 'WuLiangYe',
    })
    assert resp.status_code == 201

    # B adds to watchlist
    resp = await client.post('/api/watchlist', headers=auth_headers(token_b), json={
        'stock_code': '600519', 'stock_name': 'MaoTai',
    })
    assert resp.status_code == 201

    # A sees only their stock
    resp = await client.get('/api/watchlist', headers=auth_headers(token_a))
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['stock_code'] == '000858'

    # B sees only their stock
    resp = await client.get('/api/watchlist', headers=auth_headers(token_b))
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['stock_code'] == '600519'

    # B tries to delete A's stock -> 404
    resp = await client.delete('/api/watchlist/000858', headers=auth_headers(token_b))
    assert resp.status_code == 404


async def test_watchlist_same_stock_different_users(client, db_session):
    """Two users can watch the same stock without conflict."""
    token_a, token_b = await _setup_two_users(client, db_session)

    resp = await client.post('/api/watchlist', headers=auth_headers(token_a), json={
        'stock_code': '600519', 'stock_name': 'MaoTai',
    })
    assert resp.status_code == 201

    resp = await client.post('/api/watchlist', headers=auth_headers(token_b), json={
        'stock_code': '600519', 'stock_name': 'MaoTai',
    })
    assert resp.status_code == 201


# ------------------------------------------------------------------
# Inbox isolation
# ------------------------------------------------------------------

async def test_inbox_isolation(client, db_session):
    """User A's inbox messages are invisible to user B."""
    token_a, token_b = await _setup_two_users(client, db_session)

    # Directly insert inbox messages for each user
    from api.models.inbox_message import InboxMessage
    from sqlalchemy import select
    # Get user IDs
    resp_a = await client.get('/api/auth/me', headers=auth_headers(token_a))
    resp_b = await client.get('/api/auth/me', headers=auth_headers(token_b))
    uid_a = resp_a.json()['id']
    uid_b = resp_b.json()['id']

    msg_a = InboxMessage(user_id=uid_a, message_type='alert', title='Alert for A', content='A only')
    msg_b = InboxMessage(user_id=uid_b, message_type='system', title='System for B', content='B only')
    db_session.add_all([msg_a, msg_b])
    await db_session.commit()
    await db_session.refresh(msg_a)
    await db_session.refresh(msg_b)

    # A sees only their message
    resp = await client.get('/api/inbox', headers=auth_headers(token_a))
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['title'] == 'Alert for A'

    # B sees only their message
    resp = await client.get('/api/inbox', headers=auth_headers(token_b))
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['title'] == 'System for B'

    # A tries to access B's message by ID -> 404
    resp = await client.get(f'/api/inbox/{msg_b.id}', headers=auth_headers(token_a))
    assert resp.status_code == 404

    # A tries to delete B's message -> 404
    resp = await client.delete(f'/api/inbox/{msg_b.id}', headers=auth_headers(token_a))
    assert resp.status_code == 404


async def test_inbox_unread_count_per_user(client, db_session):
    """Unread count is per-user, not global."""
    token_a, token_b = await _setup_two_users(client, db_session)

    resp_a = await client.get('/api/auth/me', headers=auth_headers(token_a))
    resp_b = await client.get('/api/auth/me', headers=auth_headers(token_b))
    uid_a = resp_a.json()['id']
    uid_b = resp_b.json()['id']

    # Insert 3 messages for A, 1 for B
    from api.models.inbox_message import InboxMessage
    for i in range(3):
        db_session.add(InboxMessage(user_id=uid_a, message_type='alert', title=f'A-{i}'))
    db_session.add(InboxMessage(user_id=uid_b, message_type='alert', title='B-0'))
    await db_session.commit()

    resp = await client.get('/api/inbox/unread-count', headers=auth_headers(token_a))
    assert resp.json()['unread_count'] == 3

    resp = await client.get('/api/inbox/unread-count', headers=auth_headers(token_b))
    assert resp.json()['unread_count'] == 1


# ------------------------------------------------------------------
# No auth -> 401
# ------------------------------------------------------------------

async def test_protected_routes_require_auth(client, db_session):
    """Protected endpoints return 401/403 without a token."""
    routes = [
        ('GET', '/api/positions'),
        ('GET', '/api/watchlist'),
        ('GET', '/api/inbox'),
        ('GET', '/api/inbox/unread-count'),
        ('GET', '/api/auth/me'),
    ]
    for method, path in routes:
        resp = await client.request(method, path)
        assert resp.status_code in (401, 403), f'{method} {path} returned {resp.status_code}'
