# -*- coding: utf-8 -*-
"""
Celery tasks for annual report ingestion into ChromaDB.
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks')


@celery_app.task(bind=True, name='tasks.ingest_annual_reports', max_retries=2)
def ingest_annual_reports_task(
    self,
    stock_code: str,
    stock_name: str,
    years: int = 3,
):
    """
    Download and ingest annual report PDFs for a stock into ChromaDB.

    Args:
        stock_code:  6-digit bare code or with suffix (e.g. '601872' or '601872.SH')
        stock_name:  Display name
        years:       How many years back to cover (default 3)

    Returns:
        {ingested: {year: chunk_count}, skipped: [], errors: []}
    """
    import os
    import sys
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    bare = stock_code.split('.')[0] if '.' in stock_code else stock_code
    logger.info(
        '[CELERY] ingest_annual_reports start: stock=%s(%s) years=%d',
        stock_name, bare, years,
    )

    try:
        from data_analyst.financial_fetcher.annual_report_ingest import ingest_annual_reports
        result = ingest_annual_reports(bare, stock_name, years=years)
        logger.info(
            '[CELERY] ingest_annual_reports done: stock=%s result=%s',
            bare, result,
        )
        return result
    except Exception as exc:
        logger.error(
            '[CELERY] ingest_annual_reports failed: stock=%s error=%s',
            bare, exc,
        )
        raise
