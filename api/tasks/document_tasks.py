# -*- coding: utf-8 -*-
"""
Celery task for async document ingestion (parse + embed + store in ChromaDB).
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks')


@celery_app.task(bind=True, name='tasks.ingest_document', max_retries=1, time_limit=600)
def ingest_document_task(self, doc_id: int):
    """
    Parse, embed and store a research document in ChromaDB.

    Called after the upload endpoint saves the file and DB record.
    Updates research_document.status to 'done' or 'failed'.
    """
    import os
    import sys
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    logger.info('[CELERY] ingest_document start: doc_id=%d', doc_id)

    try:
        from api.services.document_service import process_document
        result = process_document(doc_id)
        logger.info('[CELERY] ingest_document done: doc_id=%d status=%s chunks=%s',
                    doc_id, result.get('status'), result.get('chunk_count'))
        return result
    except Exception as exc:
        logger.error('[CELERY] ingest_document failed: doc_id=%d error=%s', doc_id, exc, exc_info=True)
        raise
