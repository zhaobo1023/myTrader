# -*- coding: utf-8 -*-
"""
Inbox service - helper functions for creating messages.

Uses sync pymysql for Celery worker context.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')


def create_message(
    user_id: int,
    message_type: str,
    title: str,
    content: str,
    metadata: Optional[dict] = None,
    env: str = 'online',
) -> int:
    """Create an inbox message. Returns the new message id."""
    sql = """
        INSERT INTO inbox_messages (user_id, message_type, title, content, metadata_json, is_read, created_at)
        VALUES (%s, %s, %s, %s, %s, 0, %s)
    """
    meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    execute_update(sql, (user_id, message_type, title, content, meta_json, now), env=env)

    # Get the inserted id
    result = execute_query("SELECT LAST_INSERT_ID() as id", env=env)
    msg_id = result[0]['id'] if result else 0
    logger.info('[INBOX] created message id=%s type=%s for user=%s', msg_id, message_type, user_id)
    return msg_id


def get_unread_count(user_id: int, env: str = 'online') -> int:
    """Get unread message count for a user."""
    sql = "SELECT COUNT(*) as cnt FROM inbox_messages WHERE user_id = %s AND is_read = 0"
    result = execute_query(sql, (user_id,), env=env)
    return result[0]['cnt'] if result else 0


def create_system_broadcast(
    title: str,
    content: str,
    message_type: str = 'system',
    metadata: Optional[dict] = None,
    env: str = 'online',
) -> int:
    """Send a message to all active users.

    Args:
        message_type: One of 'system', 'daily_report', 'alert', 'strategy_signal'.
    """
    users = execute_query("SELECT id FROM users WHERE is_active = 1", env=env)
    count = 0
    for user in users:
        create_message(user['id'], message_type, title, content, metadata=metadata, env=env)
        count += 1
    logger.info('[INBOX] broadcast %s message to %s users', message_type, count)
    return count
