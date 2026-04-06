# tests/unit/api/test_notification_sender.py
# -*- coding: utf-8 -*-
from unittest.mock import MagicMock
from datetime import date
from api.services.notification_sender import should_notify, build_feishu_card


def make_config(enabled=True, webhook_url='https://hook.example.com',
                notify_on_red=True, notify_on_yellow=False,
                notify_on_green=False, score_threshold=None):
    c = MagicMock()
    c.enabled = enabled
    c.webhook_url = webhook_url
    c.notify_on_red = notify_on_red
    c.notify_on_yellow = notify_on_yellow
    c.notify_on_green = notify_on_green
    c.score_threshold = score_threshold
    return c


def test_should_notify_red_signal():
    assert should_notify(make_config(notify_on_red=True), 'RED', 3.0) is True


def test_should_not_notify_yellow_by_default():
    assert should_notify(make_config(notify_on_yellow=False), 'YELLOW', 5.0) is False


def test_should_notify_by_score_threshold():
    config = make_config(notify_on_red=False, score_threshold=4.0)
    assert should_notify(config, 'NONE', 3.5) is True
    assert should_notify(config, 'NONE', 5.0) is False


def test_no_notify_when_disabled():
    assert should_notify(make_config(enabled=False), 'RED', 1.0) is False


def test_no_notify_without_webhook():
    assert should_notify(make_config(webhook_url=None), 'RED', 1.0) is False


def test_build_feishu_card_structure():
    card = build_feishu_card(
        stock_code='600519', stock_name='Maotai',
        scan_date=date(2026, 4, 6), score=7.5, score_label='Bullish',
        signals=[{'type': 'MA5 cross MA20', 'severity': 'GREEN'}],
        max_severity='GREEN',
    )
    assert card['msg_type'] == 'interactive'
    assert 'Maotai' in card['card']['header']['title']['content']
    # No emoji in content
    content = card['card']['elements'][0]['text']['content']
    assert '5D Score' in content


def test_build_feishu_card_no_signals():
    card = build_feishu_card(
        stock_code='000001', stock_name='Ping An',
        scan_date=date(2026, 4, 6), score=5.0, score_label='Neutral',
        signals=[],
        max_severity='NONE',
    )
    assert 'No significant signals' in card['card']['elements'][0]['text']['content']
