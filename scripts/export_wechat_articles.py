# -*- coding: utf-8 -*-
"""
Export articles from wechat2rss res.db (past 24h) to JSON.
Run on server: python3 /root/app/scripts/export_wechat_articles.py

Output: /root/app/output/article_export/YYYY-MM-DD.json
"""
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.environ.get('WECHAT_RSS_DB', '/root/wechat2rss/data/res.db')
OUTPUT_DIR = os.environ.get('ARTICLE_EXPORT_DIR', os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'article_export'))

TITLE_BLACKLIST = [
    r'^[【\[].*?[】\]].*(?:福利|恭喜|红包)',
    r'^.*(?:招聘|活动报名|课程|直播回放|互推|关注.*回复|扫码|入群|广告|推广|转发抽奖)',
    r'^测试',
]

MIN_CONTENT_LEN = 1500
MAX_PER_FEED = 3


def is_blacklisted(title):
    for pat in TITLE_BLACKLIST:
        if re.search(pat, title):
            return True
    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    target_date = datetime.now().strftime('%Y-%m-%d')
    cutoff = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    feeds = {r['feed_id']: r['name'] for r in conn.execute('SELECT feed_id, name FROM rsses').fetchall()}

    # Filter by article publish time (created), past 24h
    articles = conn.execute("""
        SELECT a.id, a.feed_id, a.title, a.content, a.url, a.created_at, a.o_id, a.created
        FROM articles a
        WHERE a.created >= ?
        ORDER BY a.feed_id, a.created DESC
    """, (cutoff,)).fetchall()

    conn.close()

    # Group by feed, apply per-feed limit
    feed_articles = {}
    for a in articles:
        fid = a['feed_id']
        if fid not in feed_articles:
            feed_articles[fid] = []
        feed_articles[fid].append(dict(a))

    result = []
    stats = {'total_raw': len(articles), 'filtered_short': 0, 'filtered_blacklist': 0, 'filtered_limit': 0}

    for fid, arts in feed_articles.items():
        feed_name = feeds.get(fid, 'unknown')
        arts.sort(key=lambda x: len(x.get('content') or ''), reverse=True)
        kept = 0

        for a in arts:
            content = a.get('content') or ''
            title = a.get('title') or ''

            if len(content) < MIN_CONTENT_LEN:
                stats['filtered_short'] += 1
                continue
            if is_blacklisted(title):
                stats['filtered_blacklist'] += 1
                continue
            if kept >= MAX_PER_FEED:
                stats['filtered_limit'] += 1
                continue

            result.append({
                'article_id': a['id'],
                'feed_id': fid,
                'feed_name': feed_name,
                'title': title,
                'content': content[:8000],
                'url': a.get('url', ''),
                'original_id': a.get('o_id', ''),
                'created_at': a.get('created_at', ''),
                'published_at': a.get('created', ''),
                'content_length': len(content),
            })
            kept += 1

    result.sort(key=lambda x: x['content_length'], reverse=True)

    output_path = os.path.join(OUTPUT_DIR, '{}.json'.format(target_date))
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'export_date': target_date,
            'cutoff': cutoff,
            **stats,
            'articles': result,
        }, f, ensure_ascii=False)

    print('Exported {} articles to {} (raw={}, short={}, blacklist={}, limit={})'.format(
        len(result), output_path, stats['total_raw'], stats['filtered_short'],
        stats['filtered_blacklist'], stats['filtered_limit']))


if __name__ == '__main__':
    main()
