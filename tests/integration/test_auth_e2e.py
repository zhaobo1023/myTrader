# -*- coding: utf-8 -*-
"""
P4-T1: End-to-end authentication flow.

admin creates invite code -> user registers -> login -> access /me -> 401 without token
"""
import pytest
import pytest_asyncio

from tests.integration.conftest import (
    create_admin_user, create_invite_code, register_user, login_user, auth_headers,
)

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# Core auth flow
# ------------------------------------------------------------------

async def test_full_auth_flow(client, db_session):
    """admin creates invite -> user registers -> login -> /me works -> no-token 401."""
    # 1. Seed admin
    admin = await create_admin_user(db_session)

    # 2. Create invite code
    invite = await create_invite_code(db_session, admin.id, code='HELLO123')

    # 3. Register with invite code
    reg = await register_user(client, 'alice', 'pass1234', 'HELLO123')
    assert 'access_token' in reg
    assert 'refresh_token' in reg

    # 4. Login
    token = await login_user(client, 'alice', 'pass1234')
    assert token

    # 5. Access /me
    resp = await client.get('/api/auth/me', headers=auth_headers(token))
    assert resp.status_code == 200
    me = resp.json()
    assert me['username'] == 'alice'
    assert me['role'] == 'user'
    assert me['is_active'] is True

    # 6. No token -> 401
    resp = await client.get('/api/auth/me')
    assert resp.status_code in (401, 403)


async def test_invalid_invite_code_rejected(client, db_session):
    """Registration with a non-existent invite code returns 400."""
    await create_admin_user(db_session)
    resp = await client.post('/api/auth/register', json={
        'username': 'bob',
        'password': 'pass1234',
        'invite_code': 'NOSUCHCODE',
    })
    assert resp.status_code == 400
    assert 'Invalid' in resp.json()['detail']


async def test_expired_invite_code_rejected(client, db_session):
    """Registration with an expired invite code returns 400."""
    from datetime import datetime, timedelta
    admin = await create_admin_user(db_session)

    from api.models.invite_code import InviteCode
    invite = InviteCode(
        code='EXPIRED01',
        created_by=admin.id,
        max_uses=1,
        use_count=0,
        is_active=True,
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(invite)
    await db_session.commit()

    resp = await client.post('/api/auth/register', json={
        'username': 'charlie',
        'password': 'pass1234',
        'invite_code': 'EXPIRED01',
    })
    assert resp.status_code == 400
    assert 'expired' in resp.json()['detail'].lower()


async def test_fully_used_invite_code_rejected(client, db_session):
    """Registration with a fully-consumed invite code returns 400."""
    admin = await create_admin_user(db_session)

    from api.models.invite_code import InviteCode
    invite = InviteCode(
        code='USED0001',
        created_by=admin.id,
        max_uses=1,
        use_count=1,
        is_active=True,
    )
    db_session.add(invite)
    await db_session.commit()

    resp = await client.post('/api/auth/register', json={
        'username': 'dave',
        'password': 'pass1234',
        'invite_code': 'USED0001',
    })
    assert resp.status_code == 400
    assert 'fully used' in resp.json()['detail'].lower()


async def test_duplicate_username_rejected(client, db_session):
    """Registering the same username twice returns 409."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='INV001')
    await register_user(client, 'eve', 'pass1234', 'INV001')

    # Create another invite code for second attempt
    await create_invite_code(db_session, admin.id, code='INV002')
    resp = await client.post('/api/auth/register', json={
        'username': 'eve',
        'password': 'pass5678',
        'invite_code': 'INV002',
    })
    assert resp.status_code == 409


async def test_wrong_password_rejected(client, db_session):
    """Login with wrong password returns 401."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='INV003')
    await register_user(client, 'frank', 'correctpass', 'INV003')

    resp = await client.post('/api/auth/login', json={
        'username': 'frank',
        'password': 'wrongpass',
    })
    assert resp.status_code == 401


async def test_refresh_token_flow(client, db_session):
    """Refresh token produces a new valid access token."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='INV004')
    reg = await register_user(client, 'grace', 'pass1234', 'INV004')

    refresh = reg['refresh_token']
    resp = await client.post('/api/auth/refresh', json={'refresh_token': refresh})
    assert resp.status_code == 200
    new_token = resp.json()['access_token']

    # New token works
    resp = await client.get('/api/auth/me', headers=auth_headers(new_token))
    assert resp.status_code == 200
    assert resp.json()['username'] == 'grace'


async def test_update_profile(client, db_session):
    """PUT /me updates display_name and email."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='INV005')
    reg = await register_user(client, 'hank', 'pass1234', 'INV005')
    token = reg['access_token']

    resp = await client.put('/api/auth/me', headers=auth_headers(token), json={
        'display_name': 'Hank Z',
        'email': 'hank@example.com',
    })
    assert resp.status_code == 200
    assert resp.json()['display_name'] == 'Hank Z'
    assert resp.json()['email'] == 'hank@example.com'


async def test_change_password(client, db_session):
    """POST /change-password then login with new password."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='INV006')
    reg = await register_user(client, 'iris', 'oldpass123', 'INV006')
    token = reg['access_token']

    # Change password
    resp = await client.post('/api/auth/change-password', headers=auth_headers(token), json={
        'current_password': 'oldpass123',
        'new_password': 'newpass456',
    })
    assert resp.status_code == 200

    # Old password no longer works
    resp = await client.post('/api/auth/login', json={
        'username': 'iris', 'password': 'oldpass123',
    })
    assert resp.status_code == 401

    # New password works
    token2 = await login_user(client, 'iris', 'newpass456')
    assert token2
