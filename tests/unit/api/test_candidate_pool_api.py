# -*- coding: utf-8 -*-
"""
Unit tests for /api/candidate-pool/* endpoints (tags + stocks).
Uses FastAPI TestClient with mocked DB.
"""
import json
import sys
import os
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_test_app():
    from api.routers.candidate_pool import router
    from api.middleware.auth import get_current_user

    class _FakeUser:
        id = 1
        email = 'test@test.com'
        display_name = 'Test'
        is_active = True
        is_admin = False

    async def _override_auth():
        return _FakeUser()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _override_auth
    return app


def _make_stock_row(code='000001.SZ', name='TestCo', status='watching', source_type='manual'):
    return {
        'id': 1,
        'user_id': 1,
        'stock_code': code,
        'stock_name': name,
        'source_type': source_type,
        'source_detail': None,
        'entry_snapshot': json.dumps({'rps_250': 85, 'close': 10.5}),
        'add_date': '2026-04-24',
        'status': status,
        'memo': None,
        'created_at': '2026-04-24 10:00:00',
        # monitor fields (joined)
        'monitor_date': '2026-04-24',
        'close': 11.0,
        'rps_250': 88.0,
        'rps_120': 75.0,
        'rps_20': 60.0,
        'rps_slope': 0.3,
        'ma20': 10.8,
        'ma60': 10.5,
        'ma250': 9.8,
        'volume_ratio': 1.2,
        'rsi': 55.0,
        'macd_dif': 0.1,
        'macd_dea': 0.05,
        'pct_since_add': 4.76,
        'rps_change': 3.0,
        'monitor_signals': json.dumps(['RPS强势']),
        'alert_level': 'green',
    }


def _make_tag_row(tag_id=1, name='test_tag', color='#5e6ad2'):
    return {
        'id': tag_id,
        'name': name,
        'color': color,
        'created_at': '2026-04-24 10:00:00',
        'stock_count': 2,
    }


def _make_stock_tag_row(stock_id=1, tag_id=1, name='test_tag', color='#5e6ad2'):
    return {
        'stock_id': stock_id,
        'tag_id': tag_id,
        'name': name,
        'color': color,
    }


class TestCandidatePoolStockAPI(unittest.TestCase):

    def setUp(self):
        self.eq_patcher = patch('api.services.candidate_pool_service.execute_query')
        self.eu_patcher = patch('api.services.candidate_pool_service.execute_update')
        self.em_patcher = patch('api.services.candidate_pool_service.execute_many')
        self.mock_eq = self.eq_patcher.start()
        self.mock_eu = self.eu_patcher.start()
        self.mock_em = self.em_patcher.start()
        self.mock_eq.return_value = []
        self.mock_eq.side_effect = None
        self.mock_eu.return_value = None
        self.mock_em.return_value = None

        app = _build_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.eq_patcher.stop()
        self.eu_patcher.stop()
        self.em_patcher.stop()

    # -- List stocks --

    def test_list_stocks_empty(self):
        self.mock_eq.return_value = []
        resp = self.client.get('/api/candidate-pool/stocks')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['data'], [])

    def test_list_stocks_with_data(self):
        self.mock_eq.return_value = [_make_stock_row()]
        # Second call for tags batch load
        self.mock_eq.side_effect = [
            [_make_stock_row()],  # list_stocks
            [],  # tag batch load (no tags)
        ]
        resp = self.client.get('/api/candidate-pool/stocks')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['data'][0]['stock_code'], '000001.SZ')
        self.assertEqual(data['data'][0]['tags'], [])

    def test_list_stocks_with_tags(self):
        stock_row = _make_stock_row()
        tag_row = _make_stock_tag_row(stock_id=1, tag_id=5, name='high_rps', color='#27a644')
        self.mock_eq.side_effect = [
            [stock_row],  # list_stocks
            [tag_row],    # tag batch load
        ]
        resp = self.client.get('/api/candidate-pool/stocks')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['data'][0]['tags']), 1)
        self.assertEqual(data['data'][0]['tags'][0]['name'], 'high_rps')

    # -- Add stock --

    def test_add_stock_new(self):
        self.mock_eq.side_effect = [
            [],  # check existing
            [{'id': 2}],  # get new id
        ]
        payload = {
            'stock_code': '600519.SH',
            'stock_name': 'TestCo',
            'source_type': 'manual',
        }
        resp = self.client.post('/api/candidate-pool/stocks', json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['action'], 'added')

    def test_add_stock_existing(self):
        self.mock_eq.return_value = [{'id': 1, 'status': 'watching'}]
        payload = {
            'stock_code': '000001.SZ',
            'stock_name': 'TestCo',
            'source_type': 'manual',
        }
        resp = self.client.post('/api/candidate-pool/stocks', json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['action'], 'updated')

    def test_add_stock_invalid_source(self):
        payload = {
            'stock_code': '000001.SZ',
            'stock_name': 'TestCo',
            'source_type': 'invalid',
        }
        resp = self.client.post('/api/candidate-pool/stocks', json=payload)
        self.assertEqual(resp.status_code, 400)

    # -- Update stock --

    def test_update_stock_status(self):
        self.mock_eu.return_value = None
        resp = self.client.patch('/api/candidate-pool/stocks/000001.SZ', json={'status': 'focused'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    def test_update_stock_invalid_status(self):
        resp = self.client.patch('/api/candidate-pool/stocks/000001.SZ', json={'status': 'invalid'})
        self.assertEqual(resp.status_code, 400)

    # -- Remove stock --

    def test_remove_stock(self):
        self.mock_eq.return_value = [{'id': 1}]
        resp = self.client.delete('/api/candidate-pool/stocks/000001.SZ')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    # -- History --

    def test_get_stock_history(self):
        self.mock_eq.return_value = [{
            'trade_date': '2026-04-24',
            'close': 11.0,
            'rps_250': 88.0,
            'rps_120': 75.0,
            'rps_slope': 0.3,
            'pct_since_add': 4.76,
            'rps_change': 3.0,
            'signals': json.dumps(['RPS强势']),
            'alert_level': 'green',
        }]
        resp = self.client.get('/api/candidate-pool/stocks/000001.SZ/history')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['stock_code'], '000001.SZ')
        self.assertEqual(data['count'], 1)


class TestCandidatePoolTagAPI(unittest.TestCase):

    def setUp(self):
        self.eq_patcher = patch('api.services.candidate_pool_service.execute_query')
        self.eu_patcher = patch('api.services.candidate_pool_service.execute_update')
        self.em_patcher = patch('api.services.candidate_pool_service.execute_many')
        self.mock_eq = self.eq_patcher.start()
        self.mock_eu = self.eu_patcher.start()
        self.mock_em = self.em_patcher.start()
        self.mock_eq.return_value = []
        self.mock_eq.side_effect = None
        self.mock_eu.return_value = None
        self.mock_em.return_value = None

        app = _build_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.eq_patcher.stop()
        self.eu_patcher.stop()
        self.em_patcher.stop()

    # -- List tags --

    def test_list_tags_empty(self):
        self.mock_eq.return_value = []
        resp = self.client.get('/api/candidate-pool/tags')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 0)

    def test_list_tags_with_data(self):
        self.mock_eq.return_value = [_make_tag_row(tag_id=1, name='momentum', color='#27a644')]
        resp = self.client.get('/api/candidate-pool/tags')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['data'][0]['name'], 'momentum')
        self.assertEqual(data['data'][0]['stock_count'], 2)

    # -- Create tag --

    def test_create_tag_new(self):
        self.mock_eq.side_effect = [
            [],  # check existing
            [{'id': 3}],  # get new id
        ]
        resp = self.client.post('/api/candidate-pool/tags', json={'name': 'value', 'color': '#e5534b'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['action'], 'created')
        self.assertEqual(data['name'], 'value')

    def test_create_tag_exists(self):
        self.mock_eq.return_value = [{'id': 1}]
        resp = self.client.post('/api/candidate-pool/tags', json={'name': 'test_tag'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['action'], 'exists')

    def test_create_tag_empty_name(self):
        resp = self.client.post('/api/candidate-pool/tags', json={'name': '  '})
        self.assertEqual(resp.status_code, 400)

    # -- Delete tag --

    def test_delete_tag(self):
        resp = self.client.delete('/api/candidate-pool/tags/1')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    # -- Tag stock --

    def test_tag_stock_success(self):
        self.mock_eq.side_effect = [
            [{'id': 1}],  # verify tag
            [{'id': 1}],  # verify stock
        ]
        resp = self.client.post('/api/candidate-pool/stocks/1/tags', json={'tag_id': 1})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    def test_tag_stock_unauthorized(self):
        """Tag doesn't belong to user or stock doesn't exist."""
        self.mock_eq.return_value = []  # tag not found
        resp = self.client.post('/api/candidate-pool/stocks/1/tags', json={'tag_id': 999})
        self.assertEqual(resp.status_code, 403)

    # -- Untag stock --

    def test_untag_stock(self):
        resp = self.client.delete('/api/candidate-pool/stocks/1/tags/1')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    # -- Filter by tag --

    def test_list_stocks_filtered_by_tag(self):
        stock_row = _make_stock_row()
        tag_row = _make_stock_tag_row(stock_id=1, tag_id=5, name='high_rps', color='#27a644')
        self.mock_eq.side_effect = [
            [stock_row],  # list_stocks
            [tag_row],    # tag batch load
        ]
        resp = self.client.get('/api/candidate-pool/stocks?tag_id=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # stock has tag_id=5, so it should be included
        self.assertEqual(data['count'], 1)

    def test_list_stocks_filtered_by_tag_no_match(self):
        stock_row = _make_stock_row()
        tag_row = _make_stock_tag_row(stock_id=1, tag_id=5, name='high_rps', color='#27a644')
        self.mock_eq.side_effect = [
            [stock_row],  # list_stocks
            [tag_row],    # tag batch load
        ]
        resp = self.client.get('/api/candidate-pool/stocks?tag_id=99')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # tag_id=99 doesn't match tag_id=5, so stock excluded
        self.assertEqual(data['count'], 0)


class TestCandidatePoolMonitorAPI(unittest.TestCase):

    def setUp(self):
        self.eq_patcher = patch('api.services.candidate_pool_service.execute_query')
        self.eu_patcher = patch('api.services.candidate_pool_service.execute_update')
        self.em_patcher = patch('api.services.candidate_pool_service.execute_many')
        self.mock_eq = self.eq_patcher.start()
        self.mock_eu = self.eu_patcher.start()
        self.mock_em = self.em_patcher.start()
        self.mock_eq.return_value = []
        self.mock_eq.side_effect = None
        self.mock_eu.return_value = None
        self.mock_em.return_value = None

        app = _build_test_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.eq_patcher.stop()
        self.eu_patcher.stop()
        self.em_patcher.stop()

    def test_trigger_monitor_empty(self):
        self.mock_eq.return_value = []
        resp = self.client.post('/api/candidate-pool/monitor/trigger')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['monitored'], 0)

    def test_latest_monitor(self):
        stock_row = _make_stock_row()
        self.mock_eq.side_effect = [
            [stock_row],  # list_stocks
            [],           # tag batch load
        ]
        resp = self.client.get('/api/candidate-pool/monitor/latest')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 1)


if __name__ == '__main__':
    unittest.main()
