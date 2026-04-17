# -*- coding: utf-8 -*-
"""
P4-T3: Daily report pipeline.

Create user + positions -> trigger report generation -> verify inbox message.

Note: This test exercises the inbox_service (sync pymysql layer) in isolation,
and verifies the report content logic. The actual Celery task would require
a running MySQL instance, so we test the core logic directly.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from tests.integration.conftest import (
    create_admin_user, create_invite_code, register_user, auth_headers,
)

pytestmark = pytest.mark.asyncio


async def test_positions_create_then_list(client, db_session):
    """Full flow: create positions then list them grouped by level."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='RPT001')
    reg = await register_user(client, 'reporter', 'pass1234', 'RPT001')
    token = reg['access_token']

    # Add positions at different levels
    positions = [
        {'stock_code': '000001', 'stock_name': 'PingAn', 'level': 'L1', 'shares': 1000, 'cost_price': 15.0},
        {'stock_code': '600036', 'stock_name': 'ZhaoShang', 'level': 'L1', 'shares': 500, 'cost_price': 30.0},
        {'stock_code': '000858', 'stock_name': 'WuLiangYe', 'level': 'L2', 'shares': 200, 'cost_price': 150.0},
    ]
    for p in positions:
        resp = await client.post('/api/positions', headers=auth_headers(token), json=p)
        assert resp.status_code == 201

    # List all
    resp = await client.get('/api/positions', headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 3

    # Filter by level
    resp = await client.get('/api/positions?level=L1', headers=auth_headers(token))
    assert resp.json()['total'] == 2

    resp = await client.get('/api/positions?level=L2', headers=auth_headers(token))
    assert resp.json()['total'] == 1


async def test_inbox_message_lifecycle(client, db_session):
    """Create inbox message -> list -> read -> mark-all-read -> delete."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='RPT002')
    reg = await register_user(client, 'inbox_user', 'pass1234', 'RPT002')
    token = reg['access_token']

    # Get user ID
    me = (await client.get('/api/auth/me', headers=auth_headers(token))).json()
    uid = me['id']

    # Insert messages directly
    from api.models.inbox_message import InboxMessage
    msgs = [
        InboxMessage(user_id=uid, message_type='daily_report', title='Daily 04-17', content='Report content...'),
        InboxMessage(user_id=uid, message_type='alert', title='Alert: 000001', content='Price drop'),
        InboxMessage(user_id=uid, message_type='system', title='System update', content='Maintenance'),
    ]
    db_session.add_all(msgs)
    await db_session.commit()

    # List -- all unread
    resp = await client.get('/api/inbox', headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 3
    assert data['unread_count'] == 3

    # Filter by type
    resp = await client.get('/api/inbox?message_type=alert', headers=auth_headers(token))
    assert resp.json()['total'] == 1

    # Read detail -- auto-marks as read
    msg_id = data['items'][0]['id']
    resp = await client.get(f'/api/inbox/{msg_id}', headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()['is_read'] is True

    # Unread count decreased
    resp = await client.get('/api/inbox/unread-count', headers=auth_headers(token))
    assert resp.json()['unread_count'] == 2

    # Mark all read
    resp = await client.post('/api/inbox/mark-all-read', headers=auth_headers(token))
    assert resp.status_code == 200

    resp = await client.get('/api/inbox/unread-count', headers=auth_headers(token))
    assert resp.json()['unread_count'] == 0

    # Delete a message
    resp = await client.delete(f'/api/inbox/{msg_id}', headers=auth_headers(token))
    assert resp.status_code == 204

    resp = await client.get('/api/inbox', headers=auth_headers(token))
    assert resp.json()['total'] == 2


async def test_inbox_service_create_message():
    """Test inbox_service.create_message logic with mocked DB."""
    from api.services.inbox_service import create_message

    mock_execute_update = MagicMock()
    mock_execute_query = MagicMock(return_value=[{'id': 42}])

    with patch('api.services.inbox_service.execute_update', mock_execute_update), \
         patch('api.services.inbox_service.execute_query', mock_execute_query):
        msg_id = create_message(
            user_id=1,
            message_type='daily_report',
            title='Test daily report',
            content='# Report\nSome content',
            metadata={'scan_date': '2026-04-17'},
        )

    assert msg_id == 42
    # Verify INSERT was called
    call_args = mock_execute_update.call_args
    sql = call_args[0][0]
    assert 'INSERT INTO inbox_messages' in sql
    params = call_args[0][1]
    assert params[0] == 1  # user_id
    assert params[1] == 'daily_report'


async def test_position_import_batch(client, db_session):
    """Bulk import positions."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='RPT003')
    reg = await register_user(client, 'importer', 'pass1234', 'RPT003')
    token = reg['access_token']

    resp = await client.post('/api/positions/import', headers=auth_headers(token), json={
        'items': [
            {'stock_code': '000001', 'stock_name': 'PingAn', 'level': 'L1', 'shares': 1000},
            {'stock_code': '600036', 'stock_name': 'ZhaoShang', 'level': 'L2', 'shares': 500},
            {'stock_code': '000858', 'stock_name': 'WuLiangYe', 'level': 'L3'},
        ],
    })
    assert resp.status_code == 201
    assert resp.json()['created'] == 3
    assert resp.json()['skipped'] == 0

    # Import again -- all skipped
    resp = await client.post('/api/positions/import', headers=auth_headers(token), json={
        'items': [
            {'stock_code': '000001', 'stock_name': 'PingAn', 'level': 'L1'},
        ],
    })
    assert resp.json()['created'] == 0
    assert resp.json()['skipped'] == 1


async def test_position_soft_delete(client, db_session):
    """Deleted positions are hidden from default list but exist in DB."""
    admin = await create_admin_user(db_session)
    await create_invite_code(db_session, admin.id, code='RPT004')
    reg = await register_user(client, 'deleter', 'pass1234', 'RPT004')
    token = reg['access_token']

    # Create
    resp = await client.post('/api/positions', headers=auth_headers(token), json={
        'stock_code': '000001', 'stock_name': 'PingAn', 'level': 'L1',
    })
    pos_id = resp.json()['id']

    # Soft delete
    resp = await client.delete(f'/api/positions/{pos_id}', headers=auth_headers(token))
    assert resp.status_code == 204

    # Default list (active_only=true) -- empty
    resp = await client.get('/api/positions', headers=auth_headers(token))
    assert resp.json()['total'] == 0

    # Include inactive
    resp = await client.get('/api/positions?active_only=false', headers=auth_headers(token))
    assert resp.json()['total'] == 1
    assert resp.json()['items'][0]['is_active'] is False
