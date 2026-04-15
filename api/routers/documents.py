# -*- coding: utf-8 -*-
"""
Document management router: upload, list, get, update, delete research documents.
"""
import logging
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException

from api.services import document_service

logger = logging.getLogger('myTrader.documents')

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

    try:
        result = document_service.upload_document(
            file_content=content,
            filename=file.filename or 'unknown',
            title=title,
            tags=tags,
            memo=memo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error('[doc-upload] Unexpected error: %s', e)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    if result['status'] == 'failed':
        raise HTTPException(status_code=422, detail=result.get('error', 'Processing failed'))

    return result


@router.get('')
async def list_documents(
    tags: Optional[str] = Query(default=None, description="Filter by tag substring"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List uploaded research documents."""
    return document_service.list_documents(tags=tags, limit=limit, offset=offset)


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
