# -*- coding: utf-8 -*-
"""
Sync AI-related articles from wechat2rss SQLite to MySQL ai_wechat_articles.
Filters by keyword relevance to AI / LLM / Agent topics.
"""
import os
import re
import sqlite3
import logging
from datetime import datetime
from datetime import timedelta
from html.parser import HTMLParser

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks')

# Target feed IDs: wechat2rss feed_id -> display name
TARGET_FEEDS = {
    '3975162949': '',
    '3227018184': '中国石油',
    '3957885271': '昆仑大模型',
}

WECHAT_RSS_DB = os.environ.get('WECHAT_RSS_DB', '/root/wechat2rss/data/res.db')

AI_KEYWORDS = [
    'AI', '人工智能', '大模型', 'LLM', 'Agent', '智能体',
    'GPT', 'Claude', 'DeepSeek', 'Qwen', '千问', 'Gemini',
    '机器学习', '深度学习', 'transformer', 'RAG', '向量',
    '神经网络', '自然语言', 'NLP', '语言模型', '生成式',
    'AIGC', 'ChatGPT', 'Llama', '多模态', 'MCP',
    '数智', '数字化', '智能化', '昆仑', '算力', '数字孪生',
]


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return ' '.join(p.strip() for p in self._parts if p.strip())


def _html_to_text(html: str) -> str:
    if not html:
        return ''
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        return re.sub(r'<[^>]+>', ' ', html)


def _match_keywords(title: str, text: str) -> list:
    combined = (title + ' ' + text).lower()
    return [kw for kw in AI_KEYWORDS if kw.lower() in combined]


def sync_ai_wechat_articles(days_back: int = 3) -> dict:
    """Read new articles from wechat2rss, filter by AI keywords, upsert to MySQL."""
    if not os.path.exists(WECHAT_RSS_DB):
        logger.error('[AI_WECHAT] wechat2rss DB not found: %s', WECHAT_RSS_DB)
        return {'error': 'DB not found'}

    from config.db import get_connection

    cutoff = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d %H:%M:%S')
    feed_ids_str = ','.join(f'"{fid}"' for fid in TARGET_FEEDS)

    rss_conn = sqlite3.connect(WECHAT_RSS_DB)
    rss_conn.row_factory = sqlite3.Row
    try:
        rows = rss_conn.execute(f"""
            SELECT a.o_id, a.url, a.feed_id, a.title, a.content, a.created
            FROM articles a
            WHERE a.feed_id IN ({feed_ids_str})
              AND a.created >= ?
            ORDER BY a.created DESC
        """, (cutoff,)).fetchall()
        name_rows = rss_conn.execute(
            f'SELECT feed_id, name FROM rsses WHERE feed_id IN ({feed_ids_str})'
        ).fetchall()
        feed_names = {r[0]: r[1] for r in name_rows}
    finally:
        rss_conn.close()

    logger.info('[AI_WECHAT] Fetched %d articles from wechat2rss (last %d days)', len(rows), days_back)

    mysql_conn = get_connection()
    cursor = mysql_conn.cursor()
    inserted = skipped_dup = skipped_no_kw = 0

    for row in rows:
        title = row['title'] or ''
        content_html = row['content'] or ''
        content_text = _html_to_text(content_html)
        feed_id = row['feed_id']

        matched = _match_keywords(title, content_text)
        if not matched:
            skipped_no_kw += 1
            continue

        created_str = (row['created'] or '').split('+')[0].strip()
        try:
            published_at = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            published_at = datetime.now()

        try:
            cursor.execute("""
                INSERT INTO ai_wechat_articles
                  (feed_id, feed_name, o_id, url, title, content_html, content_text,
                   published_at, matched_keywords)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  matched_keywords=VALUES(matched_keywords),
                  synced_at=CURRENT_TIMESTAMP
            """, (
                feed_id,
                feed_names.get(feed_id, TARGET_FEEDS.get(feed_id, '')),
                row['o_id'],
                row['url'] or '',
                title,
                content_html,
                content_text,
                published_at,
                ','.join(matched[:10]),
            ))
            if cursor.rowcount == 1:
                inserted += 1
            else:
                skipped_dup += 1
        except Exception as e:
            logger.error('[AI_WECHAT] Insert error o_id=%s: %s', row['o_id'], e)

    mysql_conn.commit()
    cursor.close()
    mysql_conn.close()

    result = {
        'total_fetched': len(rows),
        'inserted': inserted,
        'skipped_no_keyword': skipped_no_kw,
        'skipped_duplicate': skipped_dup,
    }
    logger.info('[AI_WECHAT] Sync done: %s', result)
    return result


@celery_app.task(name='sync_ai_wechat_articles')
def task_sync_ai_wechat_articles():
    return sync_ai_wechat_articles(days_back=3)
