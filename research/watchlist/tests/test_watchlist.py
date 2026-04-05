# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, call
from research.watchlist.manager import WatchlistManager


def test_add_invalid_tier_raises():
    mgr = WatchlistManager()
    with pytest.raises(ValueError, match='tier'):
        mgr.add('300750', tier='vip')


def test_set_tier_invalid_raises():
    mgr = WatchlistManager()
    with pytest.raises(ValueError, match='tier'):
        mgr.set_tier('300750', 'premium')


def test_add_calls_upsert():
    mgr = WatchlistManager()
    with patch('research.watchlist.manager.execute_query') as mock_eq:
        mock_eq.return_value = None
        mgr.add('300750', name='宁德时代', tier='deep', industry='锂电池')
    sql = mock_eq.call_args[0][0]
    assert 'INSERT INTO watchlist' in sql
    assert 'ON DUPLICATE KEY UPDATE' in sql


def test_remove_soft_deletes():
    mgr = WatchlistManager()
    with patch('research.watchlist.manager.execute_query') as mock_eq:
        mock_eq.return_value = None
        mgr.remove('300750')
    sql = mock_eq.call_args[0][0]
    assert 'is_active' in sql
    assert 'UPDATE watchlist' in sql


def test_list_active_no_tier_filter():
    mgr = WatchlistManager()
    fake = [{'id': 1, 'code': '300750', 'name': '宁德时代',
             'tier': 'deep', 'is_active': 1}]
    with patch('research.watchlist.manager.execute_query', return_value=fake):
        rows = mgr.list_active()
    assert rows[0]['code'] == '300750'


def test_list_active_with_tier_filter():
    mgr = WatchlistManager()
    with patch('research.watchlist.manager.execute_query', return_value=[]) as mock_eq:
        mgr.list_active(tier='deep')
    sql = mock_eq.call_args[0][0]
    assert 'tier' in sql


def test_update_thesis_truncates():
    mgr = WatchlistManager()
    long_thesis = 'x' * 300
    with patch('research.watchlist.manager.execute_query') as mock_eq:
        mock_eq.return_value = None
        mgr.update_thesis('300750', long_thesis)
    params = mock_eq.call_args[0][1]
    # First param should be the truncated thesis
    assert len(params[0]) == 200


def test_save_profile_calls_update():
    mgr = WatchlistManager()
    with patch('research.watchlist.manager.execute_query') as mock_eq:
        mock_eq.return_value = None
        mgr.save_profile('300750', 'code: "300750"')
    sql = mock_eq.call_args[0][0]
    assert 'profile_yaml' in sql
