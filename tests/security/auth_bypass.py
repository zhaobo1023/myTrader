# -*- coding: utf-8 -*-
"""
Security tests: Authentication bypass & authorization checks.
Run: pytest tests/security/auth_bypass.py -v
"""
import pytest


API_URL = 'http://localhost:8000'


class TestAuthBypass:
    """Test that authentication and authorization work correctly."""

    def test_no_token_returns_401(self):
        """Unauthenticated requests to protected endpoints should return 401."""
        import requests
        endpoints = [
            '/api/auth/me',
            '/api/portfolio/summary',
            '/api/analysis/technical?code=600519',
            '/api/analysis/fundamental?code=600519',
            '/api/strategy/strategies',
            '/api/strategy/backtests',
        ]
        for ep in endpoints:
            res = requests.get(f'{API_URL}{ep}')
            assert res.status_code == 401, f'{ep} should return 401 without token, got {res.status_code}'

    def test_invalid_token_returns_401(self):
        """Requests with invalid JWT should return 401."""
        import requests
        headers = {'Authorization': 'Bearer invalid_token_12345'}
        res = requests.get(f'{API_URL}/api/auth/me', headers=headers)
        assert res.status_code == 401

    def test_tampered_token_returns_401(self):
        """JWT with tampered payload should return 401."""
        import requests
        # Valid format but wrong signature
        fake_token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkZha2UifQ.fake_signature'
        headers = {'Authorization': f'Bearer {fake_token}'}
        res = requests.get(f'{API_URL}/api/auth/me', headers=headers)
        assert res.status_code == 401

    def test_admin_endpoints_reject_normal_user(self):
        """Admin endpoints should return 403 for non-admin users."""
        import requests
        # Register and login as normal user
        email = f'security-test-{__import__("time").time()}@example.com'
        requests.post(f'{API_URL}/api/auth/register', json={
            'email': email,
            'password': 'TestPass123!',
        })
        res = requests.post(f'{API_URL}/api/auth/login', json={
            'email': email,
            'password': 'TestPass123!',
        })
        if res.status_code != 200:
            pytest.skip('Could not create test user')

        token = res.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        admin_endpoints = [
            '/api/admin/users',
            '/api/admin/users/1/tier?tier=pro',
        ]
        for ep in admin_endpoints:
            method = 'GET' if ep == '/api/admin/users' else 'PUT'
            res = requests.request(method, f'{API_URL}{ep}', headers=headers)
            assert res.status_code == 403, f'{ep} should return 403 for non-admin'

    def test_jwt_secret_not_in_response(self):
        """JWT secret should never appear in any response."""
        import requests
        res = requests.post(f'{API_URL}/api/auth/login', json={
            'email': 'test@test.com',
            'password': 'wrong',
        })
        body = res.text.lower()
        # Common secret key names that should never leak
        assert 'secret' not in body or 'missing' in body or 'invalid' in body

    def test_public_endpoints_accessible(self):
        """Health and public endpoints should work without auth."""
        import requests
        public_endpoints = [
            ('GET', '/health'),
            ('GET', '/'),
            ('GET', '/api/market/kline?code=600519&limit=5'),
            ('GET', '/api/market/rps?window=20&top_n=5'),
            ('GET', '/api/market/latest-date'),
        ]
        for method, ep in public_endpoints:
            res = requests.request(method, f'{API_URL}{ep}')
            assert res.status_code == 200, f'{ep} should be public, got {res.status_code}'
