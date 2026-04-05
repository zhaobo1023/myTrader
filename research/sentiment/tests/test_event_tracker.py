# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch
from research.sentiment.event_tracker import SentimentEventTracker


def test_create_validates_direction():
    t = SentimentEventTracker()
    with pytest.raises(ValueError, match='direction'):
        t.create('300750', '2026-04-05', 'test', 'bad_dir', 'high', 'earnings')


def test_create_validates_magnitude():
    t = SentimentEventTracker()
    with pytest.raises(ValueError, match='magnitude'):
        t.create('300750', '2026-04-05', 'test', 'positive', 'extreme', 'earnings')


def test_create_validates_category():
    t = SentimentEventTracker()
    with pytest.raises(ValueError, match='category'):
        t.create('300750', '2026-04-05', 'test', 'positive', 'high', 'invalid_cat')


def test_create_calls_insert():
    t = SentimentEventTracker()
    with patch('research.sentiment.event_tracker.execute_query') as mock_eq:
        mock_eq.side_effect = [None, [{'id': 42}]]
        result = t.create('300750', '2026-04-05', 'test event',
                          'positive', 'high', 'earnings', 'test_source')
    assert result == 42
    assert mock_eq.call_count == 2  # INSERT + LAST_INSERT_ID


def test_list_recent_returns_rows():
    t = SentimentEventTracker()
    fake_row = {'id': 1, 'code': '300750', 'event_date': '2026-04-05',
                'event_text': 'test', 'direction': 'positive',
                'magnitude': 'high', 'category': 'earnings',
                'is_verified': 0, 'verified_result': None, 'source': None}
    with patch('research.sentiment.event_tracker.execute_query',
               return_value=[fake_row]):
        rows = t.list_recent('300750', days=30)
    assert len(rows) == 1
    assert rows[0]['direction'] == 'positive'


def test_verify_calls_update():
    t = SentimentEventTracker()
    with patch('research.sentiment.event_tracker.execute_query') as mock_eq:
        mock_eq.return_value = None
        t.verify(1, '已兑现，涨5%')
    sql = mock_eq.call_args[0][0]
    assert 'UPDATE sentiment_events' in sql
    assert 'is_verified' in sql


def test_list_recent_empty_when_no_data():
    t = SentimentEventTracker()
    with patch('research.sentiment.event_tracker.execute_query', return_value=None):
        rows = t.list_recent('300750')
    assert rows == []
