# -*- coding: utf-8 -*-
"""
Unit tests for strategist/daily_report/run_daily.py

Tests the core data-processing functions in isolation (no DB, no LLM calls).
"""
import sys
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from strategist.daily_report.run_daily import (
    _fetch_tech_data,
    _format_stock_block,
    _build_prompt,
    _send_to_inbox,
    run,
)

TODAY = date(2026, 4, 24)
TODAY_STR = '2026-04-24'
STALE_DATE = '2026-04-22'


# ---------------------------------------------------------------------------
# _fetch_tech_data
# ---------------------------------------------------------------------------

def _make_rows(code, num_rows=6):
    """Build fake DB rows ordered by rn=1..N (latest first)."""
    rows = []
    for rn in range(1, num_rows + 1):
        rows.append({
            'stock_code': code,
            'close_price': 100.0 - rn,   # rn=1 -> 99, rn=2 -> 98, rn=6 -> 94
            'open_price': 99.0,
            'high_price': 101.0,
            'low_price': 98.0,
            'volume': 1000 * rn,
            'trade_date': date(2026, 4, 24 - rn),
            'rn': rn,
        })
    return rows


def test_fetch_tech_data_empty_codes():
    result = _fetch_tech_data([])
    assert result == {}


def test_fetch_tech_data_normal():
    rows = _make_rows('600938.SH', 6)
    with patch('strategist.daily_report.run_daily.execute_query', return_value=rows):
        result = _fetch_tech_data(['600938.SH'])

    assert '600938.SH' in result
    t = result['600938.SH']
    assert t['close'] == 99.0          # rn=1
    # chg_pct = (99 - 98) / 98 * 100 = 1.02
    assert t['chg_pct'] == pytest.approx(1.02, abs=0.01)
    # chg_5d_pct = (99 - 94) / 94 * 100 = 5.32
    assert t['chg_5d_pct'] == pytest.approx(5.32, abs=0.01)
    # vol_ratio = 1000 / 2000 = 0.5
    assert t['vol_ratio'] == pytest.approx(0.5, abs=0.01)


def test_fetch_tech_data_single_row():
    """Only one row: prev/day5 unavailable -> chg_pct and chg_5d_pct are None."""
    rows = _make_rows('000001.SZ', 1)
    with patch('strategist.daily_report.run_daily.execute_query', return_value=rows):
        result = _fetch_tech_data(['000001.SZ'])

    t = result['000001.SZ']
    assert t['chg_pct'] is None
    assert t['chg_5d_pct'] is None


def test_fetch_tech_data_db_error():
    """DB exception should be caught and return empty dict."""
    with patch('strategist.daily_report.run_daily.execute_query',
               side_effect=Exception('db error')):
        result = _fetch_tech_data(['600519.SH'])
    assert result == {}


# ---------------------------------------------------------------------------
# _format_stock_block
# ---------------------------------------------------------------------------

def _make_position(code='600938.SH', name='中国海油', level='L1', cost=35.0):
    return {'stock_code': code, 'stock_name': name, 'level': level,
            'shares': 1000, 'cost_price': cost}


def test_format_stock_block_fresh_data():
    """Data date == report date: no stale warning."""
    tech_map = {
        '600938.SH': {
            'trade_date': TODAY_STR, 'close': 37.5,
            'chg_pct': 1.1, 'chg_5d_pct': 2.3, 'vol_ratio': 1.2,
        }
    }
    lines = _format_stock_block(_make_position(), tech_map, {}, TODAY)
    header = lines[0]
    assert '[数据陈旧' not in header
    tech_line = lines[1]
    assert '数据日期=' + TODAY_STR in tech_line
    assert '[数据日期=' not in tech_line  # no stale marker


def test_format_stock_block_stale_data():
    """Data date != report date: stale warning appears."""
    tech_map = {
        '600938.SH': {
            'trade_date': STALE_DATE, 'close': 37.09,
            'chg_pct': -0.93, 'chg_5d_pct': 0.54, 'vol_ratio': 1.09,
        }
    }
    lines = _format_stock_block(_make_position(), tech_map, {}, TODAY)
    header = lines[0]
    assert '[数据陈旧' in header
    tech_line = lines[1]
    assert f'[数据日期={STALE_DATE}' in tech_line
    assert '非' + TODAY_STR in tech_line


def test_format_stock_block_no_market_data():
    """Stock not in tech_map: outputs 'no data' and marks stale."""
    lines = _format_stock_block(_make_position(), {}, {}, TODAY)
    assert '暂无行情数据' in lines[1]
    # header must carry stale warning since data is missing
    assert '[数据陈旧' in lines[0]


def test_format_stock_block_pnl():
    """cost_price present: 持仓盈亏 appears in tech line."""
    tech_map = {
        '600938.SH': {
            'trade_date': TODAY_STR, 'close': 40.0,
            'chg_pct': 1.0, 'chg_5d_pct': 2.0, 'vol_ratio': 1.0,
        }
    }
    lines = _format_stock_block(_make_position(cost=35.0), tech_map, {}, TODAY)
    # pnl = (40 - 35) / 35 * 100 = 14.29%
    assert '持仓盈亏=+14.29%' in lines[1]


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

def _make_user_info(positions):
    return {'user_id': 1, 'display_name': 'TestUser', 'email': '', 'positions': positions}


def test_build_prompt_no_stale():
    pos = [_make_position('600938.SH', level='L1')]
    tech_map = {'600938.SH': {'trade_date': TODAY_STR, 'close': 37.5,
                               'chg_pct': 1.0, 'chg_5d_pct': 2.0, 'vol_ratio': 1.0}}
    prompt = _build_prompt(_make_user_info(pos), tech_map, {}, TODAY)
    assert '[数据警告]' not in prompt
    assert '[数据缺失]' not in prompt
    assert '## 重点关注' in prompt


def test_build_prompt_stale_warning():
    pos = [_make_position('600938.SH', level='L2')]
    tech_map = {'600938.SH': {'trade_date': STALE_DATE, 'close': 37.09,
                               'chg_pct': -0.93, 'chg_5d_pct': 0.54, 'vol_ratio': 1.09}}
    prompt = _build_prompt(_make_user_info(pos), tech_map, {}, TODAY)
    assert '[数据警告]' in prompt
    assert '600938.SH' in prompt


def test_build_prompt_missing_data():
    pos = [_make_position('999999.SH', level='L3')]
    prompt = _build_prompt(_make_user_info(pos), {}, {}, TODAY)
    assert '[数据缺失]' in prompt
    assert '999999.SH' in prompt


def test_build_prompt_level_grouping():
    positions = [
        _make_position('000001.SZ', level='L1'),
        _make_position('000002.SZ', level='L2'),
        _make_position('000003.SZ', level='L3'),
    ]
    tech_map = {code: {'trade_date': TODAY_STR, 'close': 10.0,
                        'chg_pct': 0.0, 'chg_5d_pct': 0.0, 'vol_ratio': 1.0}
                for code in ['000001.SZ', '000002.SZ', '000003.SZ']}
    prompt = _build_prompt(_make_user_info(positions), tech_map, {}, TODAY)
    assert '## 重点关注（L1 仓位）' in prompt
    assert '## 一般关注（L2 仓位）' in prompt
    # L3 falls into others section
    assert '## 观察仓位' in prompt


# ---------------------------------------------------------------------------
# _send_to_inbox
# ---------------------------------------------------------------------------

def test_send_to_inbox_dry_run():
    """dry_run=True must NOT call execute_update."""
    with patch('strategist.daily_report.run_daily.execute_update') as mock_up:
        _send_to_inbox(1, 'title', 'content', dry_run=True)
    mock_up.assert_not_called()


def test_send_to_inbox_normal():
    with patch('strategist.daily_report.run_daily.execute_update') as mock_up:
        _send_to_inbox(1, 'title', 'content', dry_run=False)
    mock_up.assert_called_once()


def test_send_to_inbox_db_error_no_raise():
    """DB error must be caught, not propagated."""
    with patch('strategist.daily_report.run_daily.execute_update',
               side_effect=Exception('db error')):
        _send_to_inbox(1, 'title', 'content', dry_run=False)  # should not raise


# ---------------------------------------------------------------------------
# run() - per-user stale title
# ---------------------------------------------------------------------------

def test_run_title_per_user_independent():
    """User A's stale stocks must not affect User B's report title."""
    users = [
        {'user_id': 1, 'display_name': 'A', 'email': '',
         'positions': [{'stock_code': 'STALE.SH', 'stock_name': 'StaleStock',
                        'level': 'L1', 'shares': 100, 'cost_price': 10.0}]},
        {'user_id': 2, 'display_name': 'B', 'email': '',
         'positions': [{'stock_code': 'FRESH.SH', 'stock_name': 'FreshStock',
                        'level': 'L1', 'shares': 100, 'cost_price': 10.0}]},
    ]
    tech_map = {
        'STALE.SH': {'trade_date': STALE_DATE, 'close': 10.0,
                     'chg_pct': -1.0, 'chg_5d_pct': 0.0, 'vol_ratio': 1.0},
        'FRESH.SH': {'trade_date': TODAY_STR, 'close': 10.0,
                     'chg_pct': 1.0, 'chg_5d_pct': 0.0, 'vol_ratio': 1.0},
    }
    sent_titles = {}

    def fake_send(user_id, title, content, dry_run=False):
        sent_titles[user_id] = title

    with patch('strategist.daily_report.run_daily._get_active_users_with_positions',
               return_value=users), \
         patch('strategist.daily_report.run_daily._fetch_tech_data',
               return_value=tech_map), \
         patch('strategist.daily_report.run_daily._ensure_today_announcements'), \
         patch('strategist.daily_report.run_daily._get_announcements', return_value={}), \
         patch('strategist.daily_report.run_daily._generate_report',
               return_value='report content'), \
         patch('strategist.daily_report.run_daily._send_to_inbox',
               side_effect=fake_send):
        run(dry_run=False, target_date=TODAY)

    assert '[部分数据非今日' in sent_titles[1], 'User A should have stale warning'
    assert '[部分数据非今日' not in sent_titles[2], 'User B should NOT have stale warning'


def test_run_no_users():
    with patch('strategist.daily_report.run_daily._get_active_users_with_positions',
               return_value=[]):
        result = run(dry_run=False, target_date=TODAY)
    assert result == {'users': 0, 'sent': 0}
