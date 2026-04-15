# -*- coding: utf-8 -*-
"""
Stock News Service — fetch, analyze, and persist per-stock news & events.

Pipeline: AKShare news -> EventDetector keywords -> LLM sentiment batch -> DB
Tables: stock_news (raw), stock_news_analysis (LLM sentiment)
"""
import json
import logging
from datetime import datetime, timedelta, date
from typing import Optional

from config.db import execute_query, execute_update, execute_many, get_connection

logger = logging.getLogger('myTrader.stock_news')

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

STOCK_NEWS_DDL = """
CREATE TABLE IF NOT EXISTS stock_news (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    source VARCHAR(100),
    url VARCHAR(500),
    publish_time DATETIME,
    event_type VARCHAR(20) COMMENT 'bullish/bearish/policy/none',
    event_category VARCHAR(50),
    event_signal VARCHAR(20) COMMENT 'strong_buy/buy/hold/sell/strong_sell',
    matched_keywords VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_title (stock_code, title(200)),
    INDEX idx_stock_date (stock_code, publish_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

STOCK_NEWS_ANALYSIS_DDL = """
CREATE TABLE IF NOT EXISTS stock_news_analysis (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL,
    analysis_date DATE NOT NULL,
    session VARCHAR(10) NOT NULL COMMENT 'daily',
    news_count INT DEFAULT 0,
    bullish_count INT DEFAULT 0,
    bearish_count INT DEFAULT 0,
    neutral_count INT DEFAULT 0,
    sentiment_score INT COMMENT '0-100 overall',
    summary TEXT COMMENT 'LLM generated summary',
    key_events TEXT COMMENT 'JSON array of key events',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, analysis_date, session),
    INDEX idx_date (analysis_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_tables():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(STOCK_NEWS_DDL)
    cursor.execute(STOCK_NEWS_ANALYSIS_DDL)
    conn.commit()
    cursor.close()
    conn.close()


# ---------------------------------------------------------------------------
# News fetching + event detection
# ---------------------------------------------------------------------------

def _fetch_news_from_eastmoney(bare_code: str) -> list[dict]:
    """
    Fetch stock news from East Money via two sources:
    1. Company announcements API (np-anotice-stock) — official filings
    2. Search API (search-api-web) — news articles

    Returns list of dicts with keys: title, content, source, url, publish_time.
    """
    import requests

    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://so.eastmoney.com/'}
    results = []
    seen_titles = set()

    # Source 1: Company announcements (reliable, structured)
    ann_url = (
        'https://np-anotice-stock.eastmoney.com/api/security/ann'
        '?stock_list={code}&page_size=20&page_index=1&ann_type=A&client_source=web'
    ).format(code=bare_code)
    try:
        resp = requests.get(ann_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get('data', {}).get('list', [])
            for item in items:
                title = item.get('title', '').strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                # Build PDF url from art_code
                art_code = item.get('art_code', '')
                ann_url_detail = 'https://data.eastmoney.com/notices/detail/{code}/{art}.html'.format(
                    code=bare_code, art=art_code) if art_code else ''
                results.append({
                    'title': title,
                    'content': item.get('title_ch', '') or '',
                    'source': '公司公告',
                    'url': ann_url_detail,
                    'publish_time': item.get('notice_date', ''),
                })
    except Exception as e:
        logger.warning('East Money announcement fetch failed: %s', e)

    # Source 2: Search news articles
    search_url = 'https://search-api-web.eastmoney.com/search/jsonp'
    for page in range(1, 3):
        params = {
            'cb': 'jQuery_cb',
            'param': json.dumps({
                'uid': '',
                'keyword': bare_code,
                'type': ['cmsArticleWebOld'],
                'client': 'web',
                'clientType': 'web',
                'clientVersion': 'curr',
                'param': {
                    'cmsArticleWebOld': {
                        'searchScope': 'default',
                        'sort': 'default',
                        'pageIndex': page,
                        'pageSize': 10,
                        'preTag': '',
                        'postTag': '',
                    }
                }
            }),
        }
        try:
            resp = requests.get(search_url, params=params, headers=headers, timeout=10)
            text = resp.text
            if '(' not in text:
                continue
            start = text.index('(') + 1
            end = text.rindex(')')
            data = json.loads(text[start:end])

            articles = (data.get('result', {})
                           .get('cmsArticleWebOld', {})
                           .get('list', []))

            for art in articles:
                title = art.get('title', '').replace('<em>', '').replace('</em>', '').strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                results.append({
                    'title': title,
                    'content': art.get('content', '').replace('<em>', '').replace('</em>', ''),
                    'source': art.get('mediaName', '') or '东方财富',
                    'url': art.get('url', ''),
                    'publish_time': art.get('date', ''),
                })
        except Exception as e:
            logger.warning('East Money search page %d failed: %s', page, e)
            break

    return results


def fetch_and_store_news(stock_code: str, days: int = 7) -> dict:
    """
    Fetch news for a stock via East Money API, detect events, and store in DB.
    Returns: {'fetched': int, 'new': int, 'events': int}
    """
    from data_analyst.sentiment.event_detector import EventDetector

    ensure_tables()

    bare_code = stock_code.split('.')[0] if '.' in stock_code else stock_code

    try:
        raw_news = _fetch_news_from_eastmoney(bare_code)
    except Exception as e:
        logger.error('News fetch failed for %s: %s', bare_code, e)
        return {'fetched': 0, 'new': 0, 'events': 0}

    if not raw_news:
        return {'fetched': 0, 'new': 0, 'events': 0}

    cutoff = datetime.now() - timedelta(days=days)
    detector = EventDetector()
    rows_to_insert = []
    event_count = 0

    for row in raw_news:
        title = str(row.get('title', '')).strip()
        content = str(row.get('content', '') or '').strip()
        source = str(row.get('source', '') or '').strip()
        url = str(row.get('url', '') or '').strip()
        pub_str = str(row.get('publish_time', '') or '').strip()

        if not title:
            continue

        pub_time = None
        if pub_str:
            try:
                pub_time = datetime.strptime(pub_str[:19], '%Y-%m-%d %H:%M:%S')
            except Exception:
                try:
                    from pandas import to_datetime as pd_to_dt
                    pub_time = pd_to_dt(pub_str).to_pydatetime()
                except Exception:
                    pass

        if pub_time and pub_time < cutoff:
            continue

        # Event detection
        text = title + ' ' + content
        event_type = 'none'
        event_category = ''
        event_signal = ''
        matched_kw = ''

        for etype in ['bullish', 'bearish', 'policy']:
            kws = detector.match_keywords(text, etype)
            if kws:
                event_type = etype
                matched_kw = ','.join(kws[:5])
                event_category = detector.get_event_category(kws[0], etype)
                sig = detector.generate_signal(etype, event_category)
                event_signal = sig.get('signal', '')
                event_count += 1
                break

        rows_to_insert.append((
            stock_code, title, content[:2000] if content else None,
            source, url, pub_time,
            event_type, event_category, event_signal, matched_kw,
        ))

    if not rows_to_insert:
        return {'fetched': len(raw_news), 'new': 0, 'events': 0}

    # Batch insert, ignore duplicates
    insert_sql = """
        INSERT IGNORE INTO stock_news
        (stock_code, title, content, source, url, publish_time,
         event_type, event_category, event_signal, matched_keywords)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.executemany(insert_sql, rows_to_insert)
        new_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error('Failed to insert news: %s', e)
        new_count = 0

    return {'fetched': len(raw_news), 'new': new_count, 'events': event_count}


# ---------------------------------------------------------------------------
# LLM analysis
# ---------------------------------------------------------------------------

LLM_PROMPT = """你是一位专业的A股投资分析师。以下是"{stock_name}"({stock_code}) 最近的新闻列表。
请进行综合分析，输出 JSON 格式（不要markdown代码块）：

{{
  "sentiment_score": 0-100的情绪分数(50中性，>50偏多，<50偏空),
  "bullish_count": 利好新闻数量,
  "bearish_count": 利空新闻数量,
  "neutral_count": 中性新闻数量,
  "summary": "200字以内的综合分析，包含：1.近期核心事件 2.情绪判断 3.需关注的风险/机会",
  "key_events": [
    {{"title": "事件标题", "type": "bullish/bearish/neutral", "impact": "一句话影响分析"}}
  ]
}}

新闻列表：
{news_text}
"""


async def analyze_stock_news(stock_code: str, stock_name: str = '') -> dict:
    """
    Run LLM analysis on recent news for a stock. Caches result in DB.
    Returns the analysis dict.
    """
    from api.services.llm_client_factory import get_llm_client

    ensure_tables()
    today_str = date.today().strftime('%Y-%m-%d')

    # Check cache
    cached = execute_query(
        "SELECT * FROM stock_news_analysis WHERE stock_code = %s AND analysis_date = %s AND session = 'daily'",
        (stock_code, today_str),
    )
    if cached:
        row = cached[0]
        return {
            'stock_code': stock_code,
            'date': today_str,
            'news_count': row['news_count'],
            'bullish_count': row['bullish_count'],
            'bearish_count': row['bearish_count'],
            'neutral_count': row['neutral_count'],
            'sentiment_score': row['sentiment_score'],
            'summary': row['summary'] or '',
            'key_events': json.loads(row['key_events']) if row['key_events'] else [],
            'cached': True,
        }

    # Fetch fresh news first
    fetch_and_store_news(stock_code, days=7)

    # Get recent news from DB
    news_rows = list(execute_query(
        """SELECT title, content, source, publish_time, event_type, event_category
           FROM stock_news
           WHERE stock_code = %s AND publish_time >= %s
           ORDER BY publish_time DESC LIMIT 30""",
        (stock_code, (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')),
    ))

    if not news_rows:
        return {
            'stock_code': stock_code, 'date': today_str,
            'news_count': 0, 'bullish_count': 0, 'bearish_count': 0, 'neutral_count': 0,
            'sentiment_score': 50, 'summary': '近期无相关新闻', 'key_events': [],
            'cached': False,
        }

    # Build news text for LLM
    lines = []
    for i, r in enumerate(news_rows[:20], 1):
        pub = r['publish_time'].strftime('%m-%d %H:%M') if r['publish_time'] else ''
        tag = ''
        if r['event_type'] and r['event_type'] != 'none':
            tag = ' [%s:%s]' % (r['event_type'], r['event_category'] or '')
        lines.append('%d. [%s] %s%s' % (i, pub, r['title'], tag))

    news_text = '\n'.join(lines)
    prompt = LLM_PROMPT.format(
        stock_name=stock_name or stock_code,
        stock_code=stock_code,
        news_text=news_text,
    )

    # Call LLM
    try:
        llm = get_llm_client()
        resp = await llm.call(prompt=prompt, temperature=0.3, max_tokens=1500)
        # Strip markdown code fences if any
        resp = resp.strip()
        if resp.startswith('```'):
            resp = resp.split('\n', 1)[-1]
        if resp.endswith('```'):
            resp = resp.rsplit('```', 1)[0]
        analysis = json.loads(resp.strip())
    except Exception as e:
        logger.error('LLM analysis failed for %s: %s', stock_code, e)
        analysis = {
            'sentiment_score': 50,
            'bullish_count': 0, 'bearish_count': 0, 'neutral_count': len(news_rows),
            'summary': '新闻已拉取，LLM分析暂时不可用: %s' % str(e)[:100],
            'key_events': [],
        }

    # Persist to DB
    result = {
        'stock_code': stock_code,
        'date': today_str,
        'news_count': len(news_rows),
        'bullish_count': analysis.get('bullish_count', 0),
        'bearish_count': analysis.get('bearish_count', 0),
        'neutral_count': analysis.get('neutral_count', 0),
        'sentiment_score': analysis.get('sentiment_score', 50),
        'summary': analysis.get('summary', ''),
        'key_events': analysis.get('key_events', []),
        'cached': False,
    }

    try:
        execute_update(
            """INSERT INTO stock_news_analysis
               (stock_code, analysis_date, session, news_count, bullish_count, bearish_count,
                neutral_count, sentiment_score, summary, key_events)
               VALUES (%s, %s, 'daily', %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 news_count=VALUES(news_count), bullish_count=VALUES(bullish_count),
                 bearish_count=VALUES(bearish_count), neutral_count=VALUES(neutral_count),
                 sentiment_score=VALUES(sentiment_score), summary=VALUES(summary),
                 key_events=VALUES(key_events)""",
            (stock_code, today_str, result['news_count'],
             result['bullish_count'], result['bearish_count'], result['neutral_count'],
             result['sentiment_score'], result['summary'],
             json.dumps(result['key_events'], ensure_ascii=False)),
        )
    except Exception as e:
        logger.error('Failed to persist analysis: %s', e)

    return result


# ---------------------------------------------------------------------------
# Query API helpers
# ---------------------------------------------------------------------------

async def get_stock_news_list(stock_code: str, days: int = 7, limit: int = 30) -> dict:
    """
    Get recent news list for a stock (from DB, with auto-fetch if stale).
    """
    ensure_tables()

    # Check if we have recent data
    latest = execute_query(
        "SELECT MAX(publish_time) as latest FROM stock_news WHERE stock_code = %s",
        (stock_code,),
    )
    latest_time = latest[0]['latest'] if latest and latest[0]['latest'] else None
    stale = latest_time is None or latest_time < datetime.now() - timedelta(hours=6)

    if stale:
        fetch_and_store_news(stock_code, days=days)

    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = list(execute_query(
        """SELECT title, content, source, url, publish_time,
                  event_type, event_category, event_signal, matched_keywords
           FROM stock_news
           WHERE stock_code = %s AND (publish_time >= %s OR publish_time IS NULL)
           ORDER BY publish_time DESC
           LIMIT %s""",
        (stock_code, cutoff, limit),
    ))

    items = []
    for r in rows:
        items.append({
            'title': r['title'],
            'content': (r['content'] or '')[:300],
            'source': r['source'] or '',
            'url': r['url'] or '',
            'publish_time': r['publish_time'].strftime('%Y-%m-%d %H:%M') if r['publish_time'] else None,
            'event_type': r['event_type'] if r['event_type'] != 'none' else None,
            'event_category': r['event_category'] or None,
            'event_signal': r['event_signal'] or None,
            'matched_keywords': r['matched_keywords'].split(',') if r['matched_keywords'] else [],
        })

    return {'stock_code': stock_code, 'count': len(items), 'items': items}
