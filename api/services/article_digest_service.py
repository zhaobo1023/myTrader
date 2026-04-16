# -*- coding: utf-8 -*-
"""
Article Digest Service -- extract structured insights from Cubox-exported articles.

Scans a directory of Markdown files, uses LLM to distill each into a one-liner
and structured digest, then persists to trade_article_digest for briefing use.
"""
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Optional

from config.db import execute_query, execute_update, get_connection
from api.services.llm_client_factory import get_llm_client

logger = logging.getLogger('myTrader.article_digest')

# ---------------------------------------------------------------------------
# LLM prompt for digest extraction
# ---------------------------------------------------------------------------

DIGEST_SYSTEM = """你是一位专业的投资研究助理。你的任务是从投资类文章中提炼出最核心的信息。

要求：
- 极度精简，每条观点压缩到一句话
- 只保留有具体数据支撑的观点，丢弃泛泛而谈的内容
- 不使用任何emoji
- 输出严格JSON格式，不要任何其他文字"""

DIGEST_PROMPT = """请从以下文章中提取核心信息，输出JSON：

```json
{{
  "title": "文章标题",
  "source_name": "来源公众号/机构名",
  "article_type": "daily_brief|macro|sector|strategy|opinion",
  "session_relevance": "morning|evening|both",
  "one_liner": "一句话总结全文核心观点（不超过50字）",
  "key_views": [
    {{"view": "具体观点（带数据）", "direction": "bullish|bearish|neutral", "sectors": ["板块"]}}
  ],
  "risk_signals": ["风险信号（如有）"],
  "data_points": ["关键数据点（带具体数字）"]
}}
```

分类说明：
- daily_brief: 每日内参、盘前/盘后速递
- macro: 宏观经济数据解读
- sector: 行业/个股深度分析
- strategy: 投资策略、仓位建议
- opinion: 市场观点、评论

session_relevance说明：
- morning: 盘前参考（隔夜/全球/宏观）
- evening: 盘后复盘参考（当日行情分析）
- both: 通用

文章内容：
{content}"""

# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def _parse_cubox_md(filepath: str) -> dict:
    """Parse a Cubox-exported Markdown file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()

    result = {'filepath': filepath, 'content': '', 'source_id': None,
              'source_url': None, 'article_date': None, 'title': ''}

    # Extract frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', raw, re.DOTALL)
    body = raw
    if fm_match:
        fm = fm_match.group(1)
        body = raw[fm_match.end():]
        # Parse id
        id_m = re.search(r'^id:\s*["\']?(\S+?)["\']?\s*$', fm, re.MULTILINE)
        if id_m:
            result['source_id'] = id_m.group(1)
        # Parse url
        url_m = re.search(r'^url:\s*(\S+)', fm, re.MULTILINE)
        if url_m:
            result['source_url'] = url_m.group(1)

    # Extract date from filename (format: xxx-YYYY-MM-DD.md)
    basename = os.path.basename(filepath)
    date_m = re.search(r'(\d{4}-\d{2}-\d{2})\.md$', basename)
    if date_m:
        result['article_date'] = date_m.group(1)

    # Extract title from first heading
    title_m = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    if title_m:
        result['title'] = title_m.group(1).strip()
    else:
        result['title'] = basename.replace('.md', '')

    # Clean body: remove image links, cubox links, excessive whitespace
    body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
    body = re.sub(r'\[Read in Cubox\].*?\n', '', body)
    body = re.sub(r'\[Read Original\].*?\n', '', body)
    body = re.sub(r'<br\s*/?\s*>', '\n', body)
    body = re.sub(r'\n{3,}', '\n\n', body)

    # Truncate to ~3000 chars to stay within LLM context budget
    if len(body) > 3000:
        body = body[:3000] + '\n\n[...truncated...]'

    result['content'] = body.strip()
    return result


# ---------------------------------------------------------------------------
# LLM digest extraction
# ---------------------------------------------------------------------------

async def _extract_digest(content: str) -> dict:
    """Call LLM to extract structured digest from article content."""
    llm = get_llm_client()
    response = await llm.call(
        prompt=DIGEST_PROMPT.format(content=content),
        system_prompt=DIGEST_SYSTEM,
        temperature=0.2,
        max_tokens=800,
    )

    # Parse JSON from response (handle markdown code blocks)
    text = response.strip()
    json_m = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if json_m:
        text = json_m.group(1)
    else:
        # Try to find raw JSON
        json_m = re.search(r'\{.*\}', text, re.DOTALL)
        if json_m:
            text = json_m.group(0)

    return json.loads(text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS trade_article_digest (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_date DATE NOT NULL,
    source_id VARCHAR(100),
    source_url VARCHAR(500),
    title VARCHAR(200) NOT NULL,
    source_name VARCHAR(100),
    article_type VARCHAR(30),
    session_relevance VARCHAR(20),
    digest_json JSON NOT NULL,
    one_liner VARCHAR(500),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_source_id (source_id),
    INDEX idx_article_date (article_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


async def digest_directory(directory: str) -> list[dict]:
    """
    Scan a directory of Cubox Markdown files, extract digests, persist to DB.

    Returns list of processed article summaries.
    """
    # Ensure table exists
    conn = get_connection('online')
    try:
        cur = conn.cursor()
        cur.execute(_TABLE_DDL)
        conn.commit()
        cur.close()
    finally:
        conn.close()

    if not os.path.isdir(directory):
        raise FileNotFoundError('Directory not found: {}'.format(directory))

    md_files = sorted([
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.endswith('.md')
    ])

    if not md_files:
        return []

    results = []
    for fpath in md_files:
        parsed = _parse_cubox_md(fpath)

        # Skip if already processed (dedup by source_id)
        if parsed['source_id']:
            existing = execute_query(
                "SELECT id FROM trade_article_digest WHERE source_id = %s",
                (parsed['source_id'],), env='online',
            )
            if existing:
                logger.info('Skipping already-digested article: %s', parsed['title'])
                results.append({
                    'title': parsed['title'],
                    'status': 'skipped',
                    'source_id': parsed['source_id'],
                })
                continue

        if not parsed['content']:
            continue

        # Extract digest via LLM
        try:
            digest = await _extract_digest(parsed['content'])
        except Exception as e:
            logger.error('Failed to digest %s: %s', parsed['title'], e)
            results.append({'title': parsed['title'], 'status': 'error', 'error': str(e)})
            continue

        # Merge parsed metadata into digest
        title = digest.get('title') or parsed['title']
        source_name = digest.get('source_name', '')
        article_type = digest.get('article_type', 'opinion')
        session_rel = digest.get('session_relevance', 'both')
        one_liner = digest.get('one_liner', '')
        article_date = parsed['article_date'] or date.today().isoformat()

        # Persist
        try:
            execute_update(
                """INSERT INTO trade_article_digest
                   (article_date, source_id, source_url, title, source_name,
                    article_type, session_relevance, digest_json, one_liner)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                    digest_json = VALUES(digest_json),
                    one_liner = VALUES(one_liner)""",
                (article_date, parsed['source_id'], parsed['source_url'],
                 title, source_name, article_type, session_rel,
                 json.dumps(digest, ensure_ascii=False), one_liner),
                env='online',
            )
        except Exception as e:
            logger.error('Failed to save digest for %s: %s', title, e)

        results.append({
            'title': title,
            'source_name': source_name,
            'article_type': article_type,
            'one_liner': one_liner,
            'status': 'ok',
        })
        logger.info('Digested: %s -> %s', title, one_liner)

    return results


def get_relevant_digests(session: str = 'morning', lookback_days: int = 1) -> list[dict]:
    """
    Get article digests relevant to the current briefing session.

    Returns only recent articles matching the session, sorted by article_type priority.
    """
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    rows = execute_query(
        """SELECT title, source_name, article_type, one_liner, digest_json
           FROM trade_article_digest
           WHERE article_date >= %s
             AND (session_relevance = %s OR session_relevance = 'both')
           ORDER BY
             FIELD(article_type, 'daily_brief', 'macro', 'sector', 'strategy', 'opinion'),
             article_date DESC
           LIMIT 5""",
        (cutoff, session),
        env='online',
    )

    results = []
    for r in rows:
        dj = r.get('digest_json')
        if isinstance(dj, str):
            try:
                dj = json.loads(dj)
            except (json.JSONDecodeError, TypeError):
                dj = {}
        elif dj is None:
            dj = {}

        results.append({
            'title': r['title'],
            'source': r.get('source_name', ''),
            'type': r.get('article_type', ''),
            'one_liner': r.get('one_liner', ''),
            'key_views': dj.get('key_views', []),
            'risk_signals': dj.get('risk_signals', []),
            'data_points': dj.get('data_points', []),
        })

    return results
