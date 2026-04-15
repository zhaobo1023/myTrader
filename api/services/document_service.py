# -*- coding: utf-8 -*-
"""
Document service: upload, parse, embed, and manage research documents.

Flow:
    upload_file() -> save to disk -> parse -> embed -> store in ChromaDB
    list_documents() / get_document() / update_document() / delete_document()
"""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from config.db import execute_query, execute_update
from investment_rag.config import RAGConfig, DEFAULT_CONFIG
from investment_rag.embeddings.embed_model import EmbeddingClient
from investment_rag.store.chroma_client import ChromaClient
from investment_rag.retrieval.bm25_retriever import BM25Retriever
from investment_rag.ingest.parsers.pdf_parser import PDFParser, Chunk
from investment_rag.ingest.parsers.md_parser import MarkdownParser
from investment_rag.ingest.parsers.docx_parser import DocxParser

logger = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.docx', '.doc', '.txt'}

# Storage root for uploaded files
UPLOAD_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'uploads', 'research',
)


def _get_parser(file_type: str, config: RAGConfig):
    """Return the appropriate parser for a file type."""
    if file_type == 'pdf':
        return PDFParser(chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    elif file_type in ('md', 'markdown'):
        return MarkdownParser(chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    elif file_type in ('docx', 'doc'):
        return DocxParser(chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    elif file_type == 'txt':
        return MarkdownParser(chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    return None


def _file_type_from_ext(filename: str) -> str:
    """Derive file_type from extension."""
    ext = Path(filename).suffix.lower()
    mapping = {
        '.pdf': 'pdf', '.md': 'md', '.markdown': 'md',
        '.docx': 'docx', '.doc': 'doc', '.txt': 'txt',
    }
    return mapping.get(ext, ext.lstrip('.'))


def upload_document(
    file_content: bytes,
    filename: str,
    title: Optional[str] = None,
    tags: Optional[str] = None,
    memo: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload and ingest a document.

    Args:
        file_content: Raw file bytes.
        filename: Original filename.
        title: Document title (defaults to filename stem).
        tags: Comma-separated tags.
        memo: User notes.

    Returns:
        Dict with document_id, status, chunk_count.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")

    file_type = _file_type_from_ext(filename)
    doc_title = title or Path(filename).stem
    file_size = len(file_content)

    # 1. Save file to disk
    month_dir = datetime.now().strftime('%Y%m')
    save_dir = os.path.join(UPLOAD_ROOT, month_dir)
    os.makedirs(save_dir, exist_ok=True)
    safe_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
    file_path = os.path.join(save_dir, safe_filename)

    with open(file_path, 'wb') as f:
        f.write(file_content)

    # 2. Create DB record
    rows = execute_query(
        """INSERT INTO research_document (title, file_type, file_size, file_path, tags, memo, status)
           VALUES (%s, %s, %s, %s, %s, %s, 'processing')""",
        (doc_title, file_type, file_size, file_path, tags, memo),
    )
    doc_id = rows  # execute_update with INSERT returns last insert id

    # Re-query to get the actual ID
    db_rows = execute_query(
        "SELECT id FROM research_document WHERE file_path = %s ORDER BY id DESC LIMIT 1",
        (file_path,),
    )
    doc_id = db_rows[0]['id'] if db_rows else 0

    logger.info('[doc-upload] Saved %s (id=%d, type=%s, size=%d)', filename, doc_id, file_type, file_size)

    # 3. Parse + embed + store
    try:
        cfg = DEFAULT_CONFIG
        parser = _get_parser(file_type, cfg)
        if not parser:
            raise ValueError(f"No parser for file type: {file_type}")

        # Parse
        chunks = parser.parse_file(file_path, source_name=filename)

        if not chunks:
            execute_update(
                "UPDATE research_document SET status = 'failed', error_msg = %s WHERE id = %s",
                ("No text content extracted", doc_id),
            )
            return {"document_id": doc_id, "status": "failed", "chunk_count": 0, "error": "No text content extracted"}

        # Build chunk IDs and metadata with doc_id and tags
        tag_list = [t.strip() for t in tags.split(',') if t.strip()] if tags else []
        for i, chunk in enumerate(chunks):
            chunk.chunk_id = f"doc_{doc_id}_{i}"
            chunk.metadata.update({
                "doc_id": doc_id,
                "title": doc_title,
                "tags": ','.join(tag_list),
            })

        # Embed
        embed_client = EmbeddingClient(cfg)
        texts = [c.text for c in chunks]
        embeddings = embed_client.embed_texts(texts)

        # Store in ChromaDB
        chroma_client = ChromaClient(cfg)
        ids = [c.chunk_id for c in chunks]
        metadatas = []
        for c in chunks:
            meta = {"source": c.source, "page": c.page}
            meta.update(c.metadata)
            meta = {k: v for k, v in meta.items() if not (isinstance(v, list) and len(v) == 0)}
            metadatas.append(meta)

        chroma_client.add_documents(
            collection_name='research',
            ids=ids,
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Build BM25 index
        bm25_retriever = BM25Retriever(k1=cfg.bm25_k1, b=cfg.bm25_b)
        bm25_docs = [
            {"id": c.chunk_id, "text": c.text, "metadata": metadatas[i]}
            for i, c in enumerate(chunks)
        ]
        bm25_retriever.build_index('research', bm25_docs)

        chunk_count = len(chunks)

        # Update DB
        execute_update(
            "UPDATE research_document SET status = 'done', chunk_count = %s WHERE id = %s",
            (chunk_count, doc_id),
        )

        logger.info('[doc-upload] Ingested %d chunks for doc_id=%d', chunk_count, doc_id)
        return {"document_id": doc_id, "status": "done", "chunk_count": chunk_count}

    except Exception as e:
        logger.error('[doc-upload] Failed for doc_id=%d: %s', doc_id, e)
        error_msg = str(e)[:500]
        execute_update(
            "UPDATE research_document SET status = 'failed', error_msg = %s WHERE id = %s",
            (error_msg, doc_id),
        )
        return {"document_id": doc_id, "status": "failed", "chunk_count": 0, "error": error_msg}


def list_documents(tags: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """List documents with optional tag filtering."""
    sql = "SELECT id, title, file_type, file_size, tags, memo, chunk_count, status, created_at, updated_at FROM research_document"
    params: list = []

    if tags:
        sql += " WHERE tags LIKE %s"
        params.append(f"%{tags}%")

    sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    rows = execute_query(sql, tuple(params))

    count_rows = execute_query("SELECT COUNT(*) as total FROM research_document")
    total = count_rows[0]['total'] if count_rows else 0

    return {
        "documents": [dict(r) for r in rows],
        "total": total,
    }


def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
    """Get a single document by ID."""
    rows = execute_query(
        "SELECT * FROM research_document WHERE id = %s", (doc_id,),
    )
    if rows:
        return dict(rows[0])
    return None


def update_document(doc_id: int, tags: Optional[str] = None, memo: Optional[str] = None) -> bool:
    """Update document tags and/or memo. Also syncs metadata in ChromaDB."""
    if not tags and not memo:
        return False

    # Build SET clause
    set_parts = []
    params: list = []
    if tags is not None:
        set_parts.append("tags = %s")
        params.append(tags)
    if memo is not None:
        set_parts.append("memo = %s")
        params.append(memo)

    params.append(doc_id)
    sql = f"UPDATE research_document SET {', '.join(set_parts)} WHERE id = %s"
    execute_update(sql, tuple(params))

    # Sync tags to ChromaDB metadata
    if tags is not None:
        try:
            cfg = DEFAULT_CONFIG
            chroma_client = ChromaClient(cfg)
            collection = chroma_client.get_collection('research')

            # Get all chunk IDs for this document
            existing = collection.get(where={"doc_id": doc_id})
            if existing and existing['ids']:
                # Update metadata for all chunks
                tag_list = [t.strip() for t in tags.split(',') if t.strip()]
                collection.update(
                    ids=existing['ids'],
                    metadatas=[{"tags": ','.join(tag_list)}] * len(existing['ids']),
                )
                logger.info('[doc-update] Synced tags for %d chunks of doc_id=%d', len(existing['ids']), doc_id)
        except Exception as e:
            logger.warning('[doc-update] Failed to sync ChromaDB metadata: %s', e)

    return True


def delete_document(doc_id: int) -> bool:
    """Delete a document: remove from ChromaDB, delete file, delete DB record."""
    doc = get_document(doc_id)
    if not doc:
        return False

    # 1. Remove from ChromaDB
    try:
        cfg = DEFAULT_CONFIG
        chroma_client = ChromaClient(cfg)
        collection = chroma_client.get_collection('research')
        existing = collection.get(where={"doc_id": doc_id})
        if existing and existing['ids']:
            collection.delete(ids=existing['ids'])
            logger.info('[doc-delete] Removed %d chunks from ChromaDB for doc_id=%d', len(existing['ids']), doc_id)
    except Exception as e:
        logger.warning('[doc-delete] Failed to remove from ChromaDB: %s', e)

    # 2. Delete file from disk
    file_path = doc.get('file_path', '')
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            logger.warning('[doc-delete] Failed to delete file: %s', e)

    # 3. Delete DB record
    execute_update("DELETE FROM research_document WHERE id = %s", (doc_id,))
    logger.info('[doc-delete] Deleted document id=%d', doc_id)

    return True
