# api/services/notification_sender.py
# -*- coding: utf-8 -*-
"""
Send Feishu/Webhook scan result notifications.
No emoji - use plain text severity labels.
"""
import logging
import requests
from datetime import date

logger = logging.getLogger('myTrader.api')


def _severity_label(severity: str) -> str:
    mapping = {'RED': '[RED]', 'YELLOW': '[WARN]', 'GREEN': '[OK]', 'NONE': '[--]'}
    return mapping.get(severity, '[--]')


def build_feishu_card(
    stock_code: str,
    stock_name: str,
    scan_date: date,
    score: float,
    score_label: str,
    signals: list,
    max_severity: str,
) -> dict:
    """Build Feishu interactive card message. No emoji in content."""
    severity_tag = _severity_label(max_severity)
    signal_lines = '\n'.join(
        f"- {_severity_label(s.get('severity', 'NONE'))} {s.get('type', '')}"
        for s in signals[:5]
    ) or '- No significant signals'

    content = (
        f"Stock: {stock_name}({stock_code})\n"
        f"Date: {scan_date}\n"
        f"5D Score: {score:.1f}/10  {score_label}\n"
        f"Signals:\n{signal_lines}"
    )

    color_map = {'RED': 'red', 'YELLOW': 'yellow', 'GREEN': 'green', 'NONE': 'grey'}
    color = color_map.get(max_severity, 'grey')

    return {
        'msg_type': 'interactive',
        'card': {
            'header': {
                'title': {'tag': 'plain_text', 'content': f'{severity_tag} 5D Scan | {stock_name}'},
                'template': color,
            },
            'elements': [
                {'tag': 'div', 'text': {'tag': 'lark_md', 'content': content}}
            ],
        },
    }


def send_webhook_notification(webhook_url: str, payload: dict) -> bool:
    """Send webhook notification. Returns True on success."""
    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning('[NOTIFY] webhook send failed: %s', e)
        return False


def should_notify(config, max_severity: str, score: float) -> bool:
    """Check user config to decide whether to send notification."""
    if not config.enabled or not config.webhook_url:
        return False
    if max_severity == 'RED' and config.notify_on_red:
        return True
    if max_severity == 'YELLOW' and config.notify_on_yellow:
        return True
    if max_severity == 'GREEN' and config.notify_on_green:
        return True
    if config.score_threshold is not None and score <= config.score_threshold:
        return True
    return False
