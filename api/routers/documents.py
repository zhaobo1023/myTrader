# -*- coding: utf-8 -*-
"""
Document management router: upload, list, get, update, delete research documents.
"""
import logging
from pathlib import PurePath
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException

from api.services import document_service
from api.tasks.document_tasks import ingest_document_task

logger = logging.getLogger('myTrader.documents')

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

router = APIRouter(prefix='/api/rag/documents', tags=['documents'])


class UpdateDocumentRequest(BaseModel):
    tags: str | None = None
    memo: str | None = None


@router.post('/upload')
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None),
    memo: Optional[str] = Form(default=None),
):
    """Upload a research document (PDF/Markdown/Word), parse and ingest into RAG."""
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")

    # Sanitize filename to prevent path traversal
    safe_name = PurePath(file.filename or 'unknown').name or 'unknown'

    try:
        result = document_service.upload_document(
            file_content=content,
            filename=safe_name,
            title=title,
            tags=tags,
            memo=memo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error('[doc-upload] Unexpected error: %s', e)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # Trigger async ingestion (parse + embed + ChromaDB)
    ingest_document_task.delay(result['document_id'])

    return result


@router.get('')
async def list_documents(
    tags: Optional[str] = Query(default=None, description="Filter by tag substring"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List uploaded research documents."""
    return document_service.list_documents(tags=tags, limit=limit, offset=offset)


@router.get('/{doc_id}/status')
async def get_document_status(doc_id: int):
    """Poll ingestion status: processing / done / failed."""
    doc = document_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": doc_id,
        "status": doc['status'],
        "chunk_count": doc.get('chunk_count') or 0,
        "error": doc.get('error_msg'),
    }


@router.get('/{doc_id}')
async def get_document(doc_id: int):
    """Get a single document by ID."""
    doc = document_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put('/{doc_id}')
async def update_document(doc_id: int, body: UpdateDocumentRequest):
    """Update document tags and/or memo."""
    doc = document_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    document_service.update_document(doc_id, tags=body.tags, memo=body.memo)
    return {"status": "ok"}


@router.delete('/{doc_id}')
async def delete_document(doc_id: int):
    """Delete a document and its chunks from ChromaDB."""
    doc = document_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    document_service.delete_document(doc_id)
    return {"status": "ok"}
