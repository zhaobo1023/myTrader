# -*- coding: utf-8 -*-
"""
One-shot script: generate categorized reports + push evening briefing to Feishu.
Run on server: python3 /root/app/scripts/run_categorized_reports.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DB_ENV', 'online')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def main():
    target_date = '2026-04-16'

    # ---- Part 1: Generate 3 categorized reports ----
    logger.info('=== Generating categorized reports ===')
    from api.services.article_digest_service import generate_categorized_reports

    try:
        results = await generate_categorized_reports(target_date=target_date)
        for r in results:
            logger.info('[OK] %s: %d articles -> %s', r['category'], r['article_count'], r['url'])
    except Exception as e:
        logger.error('[FAIL] categorized reports: %s', e, exc_info=True)

    # ---- Part 2: Push evening briefing to Feishu ----
    logger.info('=== Pushing evening briefing ===')
    from config.db import execute_query
    from api.services.feishu_doc_publisher import publish_briefing, _send_card

    rows = execute_query(
        "SELECT content, structured_data FROM trade_briefing "
        "WHERE brief_date = %s AND session = 'evening' ORDER BY id DESC LIMIT 1",
        (target_date,), env='online',
    )

    if rows:
        row = rows[0]
        content = row['content']
        structured_data = row.get('structured_data')
        if isinstance(structured_data, str):
            import json
            try:
                structured_data = json.loads(structured_data)
            except Exception:
                structured_data = None

        title = '复盘 {}'.format(target_date)
        doc = publish_briefing(
            title=title,
            content=content,
            structured_data=structured_data,
        )
        _send_card(title=title, verdict='', doc_url=doc['url'])
        logger.info('[OK] Evening briefing -> %s', doc['url'])
    else:
        logger.warning('[SKIP] No evening briefing found for %s', target_date)


if __name__ == '__main__':
    asyncio.run(main())
