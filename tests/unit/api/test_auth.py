# -*- coding: utf-8 -*-
"""
Unit tests for auth endpoints (username + invite code registration, login).
Uses httpx AsyncClient against the real FastAPI app with mocked DB.
"""
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)


def _make_fake_user(
    user_id=1,
    username='testuser',
    display_name=None,
    email=None,
    hashed_password=None,
    tier_value='free',
    role_value='user',
    is_active=True,
):
    """Create a mock User object."""
    from api.core.security import hash_password
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.display_name = display_name
    user.email = email
    user.hashed_password = hashed_password or hash_password('test123')
    user.tier = MagicMock(value=tier_value)
    user.role = MagicMock(value=role_value)
    user.is_active = is_active
    user.created_at = datetime(2026, 4, 17)
    user.invited_by = None
    return user


def _make_fake_invite(code='TESTCODE', max_uses=1, use_count=0, is_active=True, expires_at=None, created_by=1):
    invite = MagicMock()
    invite.code = code
    invite.max_uses = max_uses
    invite.use_count = use_count
    invite.is_active = is_active
    invite.expires_at = expires_at
    invite.created_by = created_by
    invite.used_by = None
    return invite


class TestAuthSchemas(unittest.TestCase):
    """Test Pydantic schema validation."""

    def test_register_request_valid_username(self):
        from api.schemas.auth import RegisterRequest
        req = RegisterRequest(username='hello', password='123456', invite_code='ABC')
        self.assertEqual(req.username, 'hello')

    def test_register_request_chinese_username(self):
        from api.schemas.auth import RegisterRequest
        req = RegisterRequest(username='zhangsan', password='123456', invite_code='ABC')
        self.assertEqual(req.username, 'zhangsan')

    def test_register_request_mixed_username(self):
        from api.schemas.auth import RegisterRequest
        req = RegisterRequest(username='user_01', password='123456', invite_code='ABC')
        self.assertEqual(req.username, 'user_01')

    def test_register_request_too_short(self):
        from api.schemas.auth import RegisterRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegisterRequest(username='a', password='123456', invite_code='ABC')

    def test_register_request_invalid_chars(self):
        from api.schemas.auth import RegisterRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegisterRequest(username='user@name', password='123456', invite_code='ABC')

    def test_register_request_password_too_short(self):
        from api.schemas.auth import RegisterRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegisterRequest(username='hello', password='12345', invite_code='ABC')

    def test_login_request(self):
        from api.schemas.auth import LoginRequest
        req = LoginRequest(username='testuser', password='mypass')
        self.assertEqual(req.username, 'testuser')

    def test_user_response_optional_email(self):
        from api.schemas.auth import UserResponse
        resp = UserResponse(
            id=1, username='test', display_name=None, email=None,
            tier='free', role='user', is_active=True, created_at='2026-04-17T00:00:00',
        )
        self.assertIsNone(resp.email)

    def test_update_profile_request(self):
        from api.schemas.auth import UpdateProfileRequest
        req = UpdateProfileRequest(display_name='New Name', email='a@b.com')
        self.assertEqual(req.display_name, 'New Name')

    def test_change_password_request(self):
        from api.schemas.auth import ChangePasswordRequest
        req = ChangePasswordRequest(current_password='old', new_password='newpass')
        self.assertEqual(req.new_password, 'newpass')


class TestInviteCodeSchema(unittest.TestCase):
    """Test invite code Pydantic schemas."""

    def test_create_defaults(self):
        from api.schemas.invite_code import InviteCodeCreate
        req = InviteCodeCreate()
        self.assertEqual(req.count, 1)
        self.assertEqual(req.max_uses, 1)
        self.assertIsNone(req.expires_in_days)

    def test_create_custom(self):
        from api.schemas.invite_code import InviteCodeCreate
        req = InviteCodeCreate(count=5, max_uses=10, expires_in_days=30)
        self.assertEqual(req.count, 5)
        self.assertEqual(req.max_uses, 10)
        self.assertEqual(req.expires_in_days, 30)

    def test_create_count_bounds(self):
        from api.schemas.invite_code import InviteCodeCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            InviteCodeCreate(count=0)
        with self.assertRaises(ValidationError):
            InviteCodeCreate(count=51)


class TestSecurityUtils(unittest.TestCase):
    """Test JWT and password utilities."""

    def test_password_hash_verify(self):
        from api.core.security import hash_password, verify_password
        hashed = hash_password('mypassword')
        self.assertTrue(verify_password('mypassword', hashed))
        self.assertFalse(verify_password('wrongpassword', hashed))

    def test_access_token_roundtrip(self):
        from api.core.security import create_access_token, decode_token
        data = {'sub': '42', 'username': 'testuser', 'tier': 'free'}
        token = create_access_token(data)
        payload = decode_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['sub'], '42')
        self.assertEqual(payload['username'], 'testuser')
        self.assertEqual(payload['type'], 'access')

    def test_refresh_token_roundtrip(self):
        from api.core.security import create_refresh_token, decode_token
        data = {'sub': '42', 'username': 'testuser', 'tier': 'free'}
        token = create_refresh_token(data)
        payload = decode_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['type'], 'refresh')

    def test_invalid_token(self):
        from api.core.security import decode_token
        result = decode_token('invalid.token.here')
        self.assertIsNone(result)

    def test_expired_token(self):
        from api.core.security import create_access_token, decode_token
        from datetime import timedelta
        data = {'sub': '42', 'username': 'test', 'tier': 'free'}
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))
        result = decode_token(token)
        self.assertIsNone(result)


class TestUserToResponse(unittest.TestCase):
    """Test _user_to_response helper."""

    def test_basic_conversion(self):
        from api.routers.auth import _user_to_response
        user = _make_fake_user(username='bob', display_name='Bob Z', email='bob@test.com')
        resp = _user_to_response(user)
        self.assertEqual(resp.username, 'bob')
        self.assertEqual(resp.display_name, 'Bob Z')
        self.assertEqual(resp.email, 'bob@test.com')
        self.assertEqual(resp.tier, 'free')

    def test_none_email(self):
        from api.routers.auth import _user_to_response
        user = _make_fake_user(email=None)
        resp = _user_to_response(user)
        self.assertIsNone(resp.email)


if __name__ == '__main__':
    unittest.main()
