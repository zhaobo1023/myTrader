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


class TestRemoveStockCleansAssociations(unittest.TestCase):
    """Verify remove_stock deletes tags AND memos (CRITICAL fix)."""

    def setUp(self):
        self.eq_patcher = patch('api.services.candidate_pool_service.execute_query')
        self.eu_patcher = patch('api.services.candidate_pool_service.execute_update')
        self.em_patcher = patch('api.services.candidate_pool_service.execute_many')
        self.mock_eq = self.eq_patcher.start()
        self.mock_eu = self.eu_patcher.start()
        self.mock_em = self.em_patcher.start()

    def tearDown(self):
        self.eq_patcher.stop()
        self.eu_patcher.stop()
        self.em_patcher.stop()

    def test_remove_stock_deletes_tags_and_memos(self):
        """remove_stock should delete tags, memos, then the stock itself."""
        from api.services.candidate_pool_service import remove_stock
        self.mock_eq.return_value = [{'id': 42}]
        result = remove_stock(user_id=1, stock_code='000001.SZ')
        self.assertTrue(result)
        # Should have 3 execute_update calls: tags, memos, stock
        self.assertEqual(self.mock_eu.call_count, 3)
        calls = [c[0][0] for c in self.mock_eu.call_args_list]
        self.assertIn('candidate_stock_tags', calls[0])
        self.assertIn('candidate_pool_memos', calls[1])
        self.assertIn('candidate_pool_stocks', calls[2])

    def test_remove_stock_not_found_still_deletes(self):
        """Even if stock not in query result, remove_stock should try DELETE."""
        from api.services.candidate_pool_service import remove_stock
        self.mock_eq.return_value = []
        result = remove_stock(user_id=1, stock_code='999999.SZ')
        self.assertTrue(result)
        # Only the final DELETE on candidate_pool_stocks
        self.assertEqual(self.mock_eu.call_count, 1)


class TestCandidatePoolMemoService(unittest.TestCase):
    """Test memo CRUD in candidate_pool_service."""

    def setUp(self):
        self.eq_patcher = patch('api.services.candidate_pool_service.execute_query')
        self.eu_patcher = patch('api.services.candidate_pool_service.execute_update')
        self.mock_eq = self.eq_patcher.start()
        self.mock_eu = self.eu_patcher.start()

    def tearDown(self):
        self.eq_patcher.stop()
        self.eu_patcher.stop()

    def test_add_memo_success(self):
        from api.services.candidate_pool_service import add_memo
        self.mock_eq.side_effect = [
            [{'id': 10}],  # stock lookup
            [{'id': 99, 'content': 'test memo', 'created_at': '2026-04-25 10:00:00'}],  # new memo
        ]
        result = add_memo(user_id=1, stock_code='000001.SZ', content='test memo')
        self.assertEqual(result['id'], 99)
        self.assertEqual(result['content'], 'test memo')
        self.mock_eu.assert_called_once()

    def test_add_memo_stock_not_found(self):
        from api.services.candidate_pool_service import add_memo
        self.mock_eq.return_value = []
        with self.assertRaises(ValueError):
            add_memo(user_id=1, stock_code='999999.SZ', content='memo')

    def test_list_memos_by_user(self):
        from api.services.candidate_pool_service import list_memos_by_user
        self.mock_eq.return_value = [
            {'id': 1, 'content': 'first', 'created_at': '2026-04-25 09:00:00'},
            {'id': 2, 'content': 'second', 'created_at': '2026-04-25 10:00:00'},
        ]
        result = list_memos_by_user(user_id=1, stock_code='000001.SZ')
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['content'], 'first')

    def test_list_memos(self):
        from api.services.candidate_pool_service import list_memos
        self.mock_eq.return_value = [
            {'id': 1, 'content': 'memo1', 'created_at': '2026-04-25 10:00:00'},
        ]
        result = list_memos(candidate_stock_id=10)
        self.assertEqual(len(result), 1)

    def test_delete_memo_success(self):
        from api.services.candidate_pool_service import delete_memo
        self.mock_eq.return_value = [{'id': 10}]
        result = delete_memo(user_id=1, stock_code='000001.SZ', memo_id=5)
        self.assertTrue(result)
        self.mock_eu.assert_called_once()

    def test_delete_memo_stock_not_found(self):
        from api.services.candidate_pool_service import delete_memo
        self.mock_eq.return_value = []
        result = delete_memo(user_id=1, stock_code='999999.SZ', memo_id=5)
        self.assertFalse(result)
        self.mock_eu.assert_not_called()


class TestDailyMonitorSignals(unittest.TestCase):
    """Test signal generation logic in run_daily_monitor."""

    def setUp(self):
        self.eq_patcher = patch('api.services.candidate_pool_service.execute_query')
        self.eu_patcher = patch('api.services.candidate_pool_service.execute_update')
        self.em_patcher = patch('api.services.candidate_pool_service.execute_many')
        self.mock_eq = self.eq_patcher.start()
        self.mock_eu = self.eu_patcher.start()
        self.mock_em = self.em_patcher.start()

    def tearDown(self):
        self.eq_patcher.stop()
        self.eu_patcher.stop()
        self.em_patcher.stop()

    def _run_monitor_with(self, rps_250=None, rps_120=None, rps_20=None,
                          rps_slope=None, close=None, ma_20=None, ma_60=None,
                          ma_250=None, rsi_14=None, volume_ratio=None,
                          macd_dif=None, macd_dea=None):
        """Helper: run monitor with one stock and specific indicator values."""
        from api.services.candidate_pool_service import run_daily_monitor

        stock = {
            'stock_code': '000001.SZ',
            'stock_name': 'TestCo',
            'add_date': '2026-04-20',
            'entry_snapshot': json.dumps({'close': 10.0, 'rps_250': 80.0}),
        }
        rps_row = {
            'stock_code': '000001.SZ',
            'rps_250': rps_250, 'rps_120': rps_120,
            'rps_20': rps_20, 'rps_slope': rps_slope,
        }
        price_row = {
            'stock_code': '000001.SZ',
            'close_price': close,
        }
        ma_row = {
            'stock_code': '000001.SZ',
            'ma_20': ma_20, 'ma_60': ma_60, 'ma_250': ma_250,
            'rsi_14': rsi_14, 'volume_ratio': volume_ratio,
            'macd_dif': macd_dif, 'macd_dea': macd_dea,
        }

        self.mock_eq.side_effect = [
            [stock],               # candidate stocks
            [{'d': '2026-04-24'}], # _latest_trade_date
            [rps_row],             # RPS batch
            [price_row],           # price batch
            [ma_row],              # MA/factor batch
        ]

        return run_daily_monitor(env='online')

    def test_rps_strong_green(self):
        result = self._run_monitor_with(rps_250=92, close=11.0, ma_20=10.5)
        self.assertEqual(result['monitored'], 1)
        # Records were written via execute_many
        self.mock_em.assert_called_once()
        # Check the record tuple (signal, alert)
        record = self.mock_em.call_args[0][1][0]
        signals_json = record[16]  # signals field
        alert = record[17]  # alert_level field
        self.assertIn('RPS强势', json.loads(signals_json))
        self.assertIn(alert, ('green', 'yellow'))  # could be yellow if other signals

    def test_rps_weak_yellow(self):
        result = self._run_monitor_with(rps_250=30)
        record = self.mock_em.call_args[0][1][0]
        signals_json = record[16]
        self.assertIn('RPS偏弱', json.loads(signals_json))

    def test_break_ma20_red(self):
        result = self._run_monitor_with(close=9.0, ma_20=10.0)
        record = self.mock_em.call_args[0][1][0]
        alert = record[17]
        signals_json = record[16]
        self.assertEqual(alert, 'red')
        self.assertIn('跌破20日线', json.loads(signals_json))

    def test_break_ma60_red(self):
        result = self._run_monitor_with(close=9.0, ma_20=8.5, ma_60=10.0)
        record = self.mock_em.call_args[0][1][0]
        alert = record[17]
        self.assertEqual(alert, 'red')
        signals = json.loads(record[16])
        self.assertIn('跌破60日线', signals)

    def test_macd_golden_cross(self):
        result = self._run_monitor_with(macd_dif=0.5, macd_dea=0.3)
        record = self.mock_em.call_args[0][1][0]
        signals = json.loads(record[16])
        self.assertIn('MACD金叉', signals)

    def test_macd_death_cross(self):
        result = self._run_monitor_with(macd_dif=0.2, macd_dea=0.5)
        record = self.mock_em.call_args[0][1][0]
        signals = json.loads(record[16])
        self.assertIn('MACD死叉', signals)

    def test_volume_spike(self):
        result = self._run_monitor_with(volume_ratio=2.5)
        record = self.mock_em.call_args[0][1][0]
        signals = json.loads(record[16])
        self.assertIn('放量异动', signals)

    def test_rsi_overbought(self):
        result = self._run_monitor_with(rsi_14=80)
        record = self.mock_em.call_args[0][1][0]
        signals = json.loads(record[16])
        self.assertIn('RSI超买', signals)

    def test_rsi_oversold(self):
        result = self._run_monitor_with(rsi_14=25)
        record = self.mock_em.call_args[0][1][0]
        signals = json.loads(record[16])
        self.assertIn('RSI超卖', signals)

    def test_no_stocks_returns_empty(self):
        from api.services.candidate_pool_service import run_daily_monitor
        self.mock_eq.return_value = []
        result = run_daily_monitor(env='online')
        self.assertEqual(result['monitored'], 0)


if __name__ == '__main__':
    unittest.main()
