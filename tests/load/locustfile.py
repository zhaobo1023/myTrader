# -*- coding: utf-8 -*-
"""
Locust load test for myTrader API endpoints.

Run: locust -f tests/load/locustfile.py --host=http://localhost:8000
"""
from locust import HttpUser, task, between


class MyTraderUser(HttpUser):
    """Simulate a typical user browsing the platform."""

    wait_time = between(1, 3)

    def on_start(self):
        """Login and store JWT token."""
        res = self.client.post('/api/auth/login', json={
            'email': 'loadtest@example.com',
            'password': 'LoadTest123!',
        })
        if res.status_code == 200:
            self.token = res.json().get('access_token', '')
            self.headers = {'Authorization': f'Bearer {self.token}'}
        else:
            self.token = ''
            self.headers = {}

    @task(5)
    def health_check(self):
        self.client.get('/health')

    @task(3)
    def get_kline(self):
        self.client.get('/api/market/kline', params={
            'code': '600519',
            'limit': 60,
        }, headers=self.headers)

    @task(3)
    def get_rps(self):
        self.client.get('/api/market/rps', params={
            'window': 120,
            'top_n': 20,
        }, headers=self.headers)

    @task(2)
    def get_analysis(self):
        self.client.get('/api/analysis/technical', params={
            'code': '600519',
        }, headers=self.headers)

    @task(1)
    def get_fundamental(self):
        self.client.get('/api/analysis/fundamental', params={
            'code': '600519',
        }, headers=self.headers)

    @task(1)
    def get_portfolio(self):
        self.client.get('/api/portfolio/summary', headers=self.headers)

    @task(1)
    def get_latest_date(self):
        self.client.get('/api/market/latest-date')
