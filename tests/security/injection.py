# -*- coding: utf-8 -*-
"""
Security tests: SQL injection & input validation.
Run: pytest tests/security/injection.py -v
"""
import pytest


API_URL = 'http://localhost:8000'


class TestSQLInjection:
    """Test that SQL injection attempts are properly handled."""

    def test_sql_injection_in_stock_code(self):
        """SQL injection in stock code parameter should not crash the server."""
        import requests
        malicious_codes = [
            "600519' OR '1'='1",
            "600519; DROP TABLE users;--",
            "600519' UNION SELECT * FROM users--",
            "1; SELECT * FROM information_schema.tables--",
        ]
        for code in malicious_codes:
            res = requests.get(f'{API_URL}/api/market/kline', params={'code': code, 'limit': 5})
            # Should return 200 with empty data or 422 validation error, NOT 500
            assert res.status_code in (200, 401, 422), \
                f'SQL injection code="{code}" returned {res.status_code}'

    def test_sql_injection_in_login(self):
        """SQL injection in login fields should not bypass authentication."""
        import requests
        payloads = [
            {"email": "' OR '1'='1' --", "password": "anything"},
            {"email": "admin'--", "password": ""},
            {"email": "'; DROP TABLE users;--", "password": "test"},
        ]
        for payload in payloads:
            res = requests.post(f'{API_URL}/api/auth/login', json=payload)
            assert res.status_code == 401, \
                f'SQL injection login should fail, got {res.status_code}'

    def test_xss_in_registration(self):
        """XSS payload in registration fields should be stored safely."""
        import requests
        xss_payloads = [
            '<script>alert("xss")</script>',
            '"><img src=x onerror=alert(1)>',
            'javascript:alert(1)',
        ]
        for payload in xss_payloads:
            email = f'xss-{abs(hash(payload))}@example.com'
            res = requests.post(f'{API_URL}/api/auth/register', json={
                'email': email,
                'password': payload,
            })
            # Should either succeed (stored safely) or reject with validation error
            assert res.status_code in (200, 201, 409, 422), \
                f'XSS registration returned {res.status_code}'

    def test_empty_required_fields_validation(self):
        """Empty required fields should return 422, not 500."""
        import requests
        res = requests.post(f'{API_URL}/api/auth/login', json={
            'email': '',
            'password': '',
        })
        assert res.status_code == 422

    def test_response_headers_no_sensitive_info(self):
        """Response headers should not contain sensitive information."""
        import requests
        res = requests.get(f'{API_URL}/health')
        headers_lower = {k.lower(): v for k, v in res.headers.items()}
        # Check for common sensitive headers that should NOT be present
        assert 'x-powered-by' not in headers_lower or 'Express' not in headers_lower.get('x-powered-by', '')
