# -*- coding: utf-8 -*-
"""
Unit tests for inbox schemas.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)


class TestInboxSchemas(unittest.TestCase):

    def test_message_response(self):
        from api.schemas.inbox import InboxMessageResponse
        resp = InboxMessageResponse(
            id=1,
            message_type='daily_report',
            title='2026-04-17 test',
            content='# Report',
            metadata_json='{"scan_date": "2026-04-17"}',
            is_read=False,
            created_at='2026-04-17T17:00:00',
        )
        self.assertEqual(resp.message_type, 'daily_report')
        self.assertFalse(resp.is_read)

    def test_message_response_null_content(self):
        from api.schemas.inbox import InboxMessageResponse
        resp = InboxMessageResponse(
            id=2,
            message_type='system',
            title='System update',
            content=None,
            metadata_json=None,
            is_read=True,
            created_at='2026-04-17T10:00:00',
        )
        self.assertIsNone(resp.content)

    def test_list_response(self):
        from api.schemas.inbox import InboxListResponse, InboxMessageResponse
        msg = InboxMessageResponse(
            id=1, message_type='alert', title='Test',
            content='body', is_read=False, created_at='2026-04-17',
        )
        resp = InboxListResponse(items=[msg], total=1, unread_count=1)
        self.assertEqual(resp.total, 1)
        self.assertEqual(resp.unread_count, 1)

    def test_unread_count_response(self):
        from api.schemas.inbox import UnreadCountResponse
        resp = UnreadCountResponse(unread_count=5)
        self.assertEqual(resp.unread_count, 5)


class TestInboxMessageModel(unittest.TestCase):

    def test_model_tablename(self):
        from api.models.inbox_message import InboxMessage
        self.assertEqual(InboxMessage.__tablename__, 'inbox_messages')

    def test_model_columns(self):
        from api.models.inbox_message import InboxMessage
        cols = {c.name for c in InboxMessage.__table__.columns}
        expected = {'id', 'user_id', 'message_type', 'title', 'content', 'metadata_json', 'is_read', 'created_at'}
        self.assertEqual(cols, expected)


class TestNotificationConfigExtension(unittest.TestCase):

    def test_new_columns_exist(self):
        from api.models.notification_config import UserNotificationConfig
        cols = {c.name for c in UserNotificationConfig.__table__.columns}
        self.assertIn('email_enabled', cols)
        self.assertIn('daily_report_enabled', cols)
        self.assertIn('daily_report_time', cols)
        self.assertIn('report_include_watchlist', cols)
        self.assertIn('report_include_positions', cols)


if __name__ == '__main__':
    unittest.main()
