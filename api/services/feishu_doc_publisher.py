# -*- coding: utf-8 -*-
"""
Feishu Document Publisher -- push briefings to Feishu docs for easy sharing.

Creates a new Feishu document for each briefing, writes structured content
using the docx v1 API, and returns a shareable link.

Requires FEISHU_APP_ID and FEISHU_APP_SECRET in .env.
"""
import logging
import re
import time
from typing import Optional

import httpx

from api.config import settings

logger = logging.getLogger('myTrader.feishu_doc')

# ---------------------------------------------------------------------------
# Auth -- tenant_access_token with simple cache
# ---------------------------------------------------------------------------

_token_cache = {'token': None, 'expires_at': 0}


def _get_tenant_token() -> str:
    """Get a cached tenant_access_token, refreshing if needed."""
    now = time.time()
    if _token_cache['token'] and _token_cache['expires_at'] > now + 300:
        return _token_cache['token']

    app_id = getattr(settings, 'FEISHU_APP_ID', '') or ''
    app_secret = getattr(settings, 'FEISHU_APP_SECRET', '') or ''
    if not app_id or not app_secret:
        raise ValueError('FEISHU_APP_ID / FEISHU_APP_SECRET not configured in .env')

    resp = httpx.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': app_id, 'app_secret': app_secret},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get('code') != 0:
        raise RuntimeError('Feishu auth failed: {}'.format(data.get('msg', data)))

    token = data['tenant_access_token']
    expire = data.get('expire', 7200)
    _token_cache['token'] = token
    _token_cache['expires_at'] = now + expire
    logger.info('Feishu tenant token refreshed, expires in %ds', expire)
    return token


def _headers() -> dict:
    return {
        'Authorization': 'Bearer {}'.format(_get_tenant_token()),
        'Content-Type': 'application/json; charset=utf-8',
    }


# ---------------------------------------------------------------------------
# Document creation
# ---------------------------------------------------------------------------

def _create_document(title: str, folder_token: str = None) -> dict:
    """Create a new Feishu document. Returns {'document_id': ..., 'url': ...}."""
    body = {'title': title}
    if folder_token:
        body['folder_token'] = folder_token

    resp = httpx.post(
        'https://open.feishu.cn/open-apis/docx/v1/documents',
        headers=_headers(),
        json=body,
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error(
            'Feishu create_document HTTP %d: body=%s request=%s',
            resp.status_code, resp.text[:500], body,
        )
        resp.raise_for_status()
    data = resp.json()
    if data.get('code') != 0:
        raise RuntimeError('Failed to create doc: {}'.format(data.get('msg', data)))

    doc = data['data']['document']
    doc_id = doc['document_id']
    url = 'https://feishu.cn/docx/{}'.format(doc_id)

    # Set public link sharing: anyone with the link can read
    _set_public_permission(doc_id)

    return {'document_id': doc_id, 'url': url}


def _set_public_permission(doc_id: str) -> None:
    """Enable 'anyone with the link can read' for a document."""
    try:
        # 1. Set doc external access setting
        resp = httpx.patch(
            'https://open.feishu.cn/open-apis/drive/v1/permissions/{}/public'.format(doc_id),
            headers=_headers(),
            params={'type': 'docx'},
            json={
                'external_access_entity': 'open',
                'security_entity': 'anyone_can_view',
                'link_share_entity': 'anyone_readable',
            },
            timeout=15,
        )
        data = resp.json()
        if data.get('code') != 0:
            logger.warning('Set public permission failed: %s', data.get('msg'))
        else:
            logger.info('Document %s set to public readable', doc_id)
    except Exception as e:
        logger.warning('Failed to set public permission for %s: %s', doc_id, e)


# ---------------------------------------------------------------------------
# Block builders -- convert markdown-like content to Feishu blocks
# ---------------------------------------------------------------------------

def _text_run(content: str, bold: bool = False) -> dict:
    """Build a text_run element."""
    run = {'content': content}
    if bold:
        run['text_element_style'] = {'bold': True}
    return {'text_run': run}


def _heading_block(level: int, text: str) -> dict:
    """Build a heading block (level 1-9 -> block_type 3-11)."""
    block_type = 2 + level  # H1=3, H2=4, H3=5 ...
    key = 'heading{}'.format(level)
    # Parse bold markers
    elements = _parse_inline(text)
    return {'block_type': block_type, key: {'elements': elements}}


def _paragraph_block(text: str) -> dict:
    """Build a text paragraph block."""
    elements = _parse_inline(text)
    return {'block_type': 2, 'text': {'elements': elements}}


def _bullet_block(text: str) -> dict:
    """Build a bullet list item block."""
    elements = _parse_inline(text)
    return {'block_type': 12, 'bullet': {'elements': elements}}


def _divider_block() -> dict:
    """Build a horizontal divider block."""
    return {'block_type': 22, 'divider': {}}


def _callout_block(text: str, bg_color: int = 2) -> dict:
    """Build a callout/quote block."""
    elements = _parse_inline(text)
    return {
        'block_type': 19,
        'callout': {
            'elements': elements,
            'background_color': bg_color,
        },
    }


def _parse_inline(text: str) -> list:
    """Parse bold (**text**) markers into text_run elements."""
    parts = re.split(r'(\*\*.*?\*\*)', text)
    elements = []
    for p in parts:
        if not p:
            continue
        if p.startswith('**') and p.endswith('**'):
            elements.append(_text_run(p[2:-2], bold=True))
        else:
            elements.append(_text_run(p))
    return elements or [_text_run(text)]


# ---------------------------------------------------------------------------
# Markdown -> Feishu blocks converter
# ---------------------------------------------------------------------------

def _markdown_to_blocks(md: str) -> list:
    """
    Convert briefing markdown to a list of Feishu document blocks.

    Supports: ### headings, - bullets, > quotes, --- dividers, paragraphs.
    """
    blocks = []
    lines = md.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # Skip empty lines
        if not line:
            i += 1
            continue

        # Divider
        if re.match(r'^-{3,}\s*$', line):
            blocks.append(_divider_block())
            i += 1
            continue

        # Headings
        h_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if h_match:
            level = len(h_match.group(1))
            blocks.append(_heading_block(level, h_match.group(2).strip()))
            i += 1
            continue

        # Blockquote
        if line.startswith('> '):
            blocks.append(_callout_block(line[2:].strip()))
            i += 1
            continue

        # Bullet
        if re.match(r'^[-*]\s+', line):
            text = re.sub(r'^[-*]\s+', '', line)
            blocks.append(_bullet_block(text))
            i += 1
            continue

        # Table lines (| ... |) -- render as plain text paragraphs
        if line.startswith('|'):
            # Skip separator lines like |---|---|
            if re.match(r'^\|[-\s|]+\|$', line):
                i += 1
                continue
            # Clean up table row into readable text
            cells = [c.strip() for c in line.strip('|').split('|')]
            blocks.append(_paragraph_block('  |  '.join(cells)))
            i += 1
            continue

        # Regular paragraph
        blocks.append(_paragraph_block(line))
        i += 1

    return blocks


# ---------------------------------------------------------------------------
# Write blocks to document
# ---------------------------------------------------------------------------

def _write_blocks(document_id: str, blocks: list) -> None:
    """Write blocks to a document, batching in groups of 50."""
    url = 'https://open.feishu.cn/open-apis/docx/v1/documents/{}/blocks/{}/children'.format(
        document_id, document_id)

    for start in range(0, len(blocks), 50):
        batch = blocks[start:start + 50]
        resp = httpx.post(
            url,
            headers=_headers(),
            json={'children': batch},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') != 0:
            logger.error('Failed to write blocks [%d:%d]: %s',
                         start, start + len(batch), data.get('msg'))
            raise RuntimeError('Write blocks failed: {}'.format(data.get('msg', data)))

    logger.info('Wrote %d blocks to document %s', len(blocks), document_id)


# ---------------------------------------------------------------------------
# Bot messaging -- send card to user
# ---------------------------------------------------------------------------

_OWNER_OPEN_ID = getattr(settings, 'FEISHU_OWNER_OPEN_ID', '') or 'ou_7c69280ea70c162707fd22da09805cea'


def _extract_verdict(content: str) -> str:
    """Extract the one-liner verdict from briefing content."""
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('**') and '|' in line:
            if line.endswith('**'):
                return line[2:-2].strip()
            return line.strip('* ')
    return ''


def _send_card(title: str, verdict: str, doc_url: str, color: str = None) -> None:
    """Send an interactive card message to the owner via bot.

    Args:
        color: Card header color. If not provided, inferred from verdict text.
    """
    import json as _json

    if color is None:
        color = 'blue'
        if '偏多' in verdict:
            color = 'green'
        elif '偏空' in verdict:
            color = 'red'
        elif '中性' in verdict:
            color = 'turquoise'

    card = {
        'config': {'wide_screen_mode': True},
        'header': {
            'title': {'tag': 'plain_text', 'content': title},
            'template': color,
        },
        'elements': [
            {
                'tag': 'div',
                'text': {'tag': 'lark_md', 'content': '**{}**'.format(verdict) if verdict else '报告已生成'},
            },
            {
                'tag': 'action',
                'actions': [{
                    'tag': 'button',
                    'text': {'tag': 'plain_text', 'content': '查看完整报告'},
                    'type': 'primary',
                    'url': doc_url,
                }],
            },
        ],
    }

    msg = {
        'receive_id': _OWNER_OPEN_ID,
        'msg_type': 'interactive',
        'content': _json.dumps(card, ensure_ascii=False),
    }

    try:
        resp = httpx.post(
            'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id',
            headers=_headers(),
            json=msg,
            timeout=15,
        )
        data = resp.json()
        if data.get('code') != 0:
            logger.warning('Bot message failed: %s', data.get('msg'))
        else:
            logger.info('Bot message sent: %s', title)
    except Exception as e:
        logger.warning('Failed to send bot message: %s', e)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def publish_briefing(
    title: str,
    content: str,
    structured_data: dict = None,
    folder_token: str = None,
) -> dict:
    """
    Publish a briefing to Feishu as a new document.

    Args:
        title: Document title (e.g. "晨报 2026-04-16")
        content: Markdown content from LLM
        structured_data: Optional structured data dict with appendix text
        folder_token: Optional Feishu folder token for destination

    Returns:
        {'document_id': str, 'url': str}
    """
    folder = folder_token or getattr(settings, 'FEISHU_FOLDER_TOKEN', None) or None

    # Create document
    doc = _create_document(title, folder_token=folder)
    doc_id = doc['document_id']
    logger.info('Created Feishu document: %s (%s)', title, doc_id)

    # Build blocks from main content
    blocks = _markdown_to_blocks(content)

    # Append structured data sections if available
    if structured_data:
        blocks.append(_divider_block())

        etf_text = structured_data.get('etf_log_bias_text', '')
        if etf_text:
            blocks.append(_heading_block(2, '附录: ETF 偏离度'))
            blocks.extend(_markdown_to_blocks(etf_text))

        limit_text = structured_data.get('limit_stock_text', '')
        if limit_text:
            blocks.append(_heading_block(2, '附录: 涨跌停明细'))
            blocks.extend(_markdown_to_blocks(limit_text))

        fear_text = structured_data.get('fear_greed_text', '')
        if fear_text:
            blocks.append(_heading_block(2, '附录: 恐贪指数'))
            blocks.extend(_markdown_to_blocks(fear_text))

    # Write all blocks
    _write_blocks(doc_id, blocks)

    logger.info('Published briefing to Feishu: %s -> %s', title, doc['url'])
    return doc


def publish_briefing_and_notify(title: str, content: str, structured_data: dict = None) -> dict:
    """
    Publish a briefing to Feishu doc and send a bot card notification.

    Convenience wrapper that combines publish_briefing + _extract_verdict + _send_card,
    so callers don't need to import private helpers.

    Returns:
        {'document_id': str, 'url': str}
    """
    doc = publish_briefing(title=title, content=content, structured_data=structured_data)
    verdict = _extract_verdict(content)
    _send_card(title, verdict, doc['url'])
    return doc


async def publish_latest_briefing(session: str = 'morning', force: bool = False) -> dict:
    """
    Generate (or load cached) briefing and publish to Feishu.

    Returns:
        {'session': str, 'date': str, 'document_id': str, 'url': str}
    """
    from api.services.global_asset_briefing import get_latest_briefing

    briefing = await get_latest_briefing(session, force=force)
    if not briefing or not briefing.get('content'):
        raise RuntimeError('No briefing content available for session: {}'.format(session))

    content = briefing['content']

    # Abort markers from global_asset_briefing data quality check
    if content.startswith('[速递中止]'):
        logger.warning('[publish] Briefing aborted by data quality: %s', content[:200])
        return {
            'session': session,
            'date': briefing.get('date', ''),
            'aborted': True,
            'reason': content[:200],
        }

    label = '晨报' if session == 'morning' else '复盘'
    title = '{} {}'.format(label, briefing.get('date', ''))

    doc = publish_briefing(
        title=title,
        content=briefing['content'],
        structured_data=briefing.get('structured_data'),
    )

    # Send bot notification
    verdict = _extract_verdict(briefing['content'])
    _send_card(title, verdict, doc['url'])

    return {
        'session': session,
        'date': briefing.get('date', ''),
        'document_id': doc['document_id'],
        'url': doc['url'],
    }
