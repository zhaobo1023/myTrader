# -*- coding: utf-8 -*-
"""
Ingest financial Markdown summaries and PDF text into ChromaDB.

Reuses investment_rag's ChromaClient and EmbeddingClient for vector
storage and embedding computation.
"""

import hashlib
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_DEFAULT_CHUNK_SIZE = 800
_DEFAULT_CHUNK_OVERLAP = 150


def _split_plain_text(
    text: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split plain text (no markdown headings) by paragraphs with sliding window.

    Used for PDF-extracted annual report text that has no ## headings.
    """
    # Split on double newlines (paragraph boundaries) or page markers
    # Remove page markers first
    text = re.sub(r'<!-- page \d+ -->', '', text)
    paragraphs = re.split(r'\n\n+', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: List[str] = []
    window: List[str] = []
    window_len = 0

    for para in paragraphs:
        para_len = len(para)
        if window and window_len + para_len > chunk_size:
            chunk = "\n\n".join(window)
            chunks.append(chunk)
            # Keep overlap
            while window and sum(len(p) for p in window) > chunk_overlap:
                removed = window.pop(0)
                window_len -= len(removed)
        window.append(para)
        window_len += para_len

    if window:
        chunk = "\n\n".join(window)
        chunks.append(chunk)

    return chunks


def _split_markdown(
    text: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split markdown by ## sections with sliding window for long sections.

    Each top-level section (## heading) becomes one or more chunks.  Short
    sections stay intact; sections that exceed *chunk_size* characters are
    further split using a sliding-window paragraph approach so that
    overlapping context is preserved across chunk boundaries.

    Args:
        text: Full markdown document text.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Character overlap between consecutive chunks.

    Returns:
        List of text chunks.
    """
    # Split on ## headings (level-2).  Keep the heading line inside the chunk.
    section_pattern = re.compile(r'^(## .+)$', re.MULTILINE)
    parts = section_pattern.split(text)

    # parts alternates: [preamble, heading, body, heading, body, ...]
    # Re-group into (heading, body) pairs.  Anything before the first ## is
    # attached to the first section as preamble.
    sections: List[str] = []
    if parts and not parts[0].startswith("##"):
        # There is a preamble (e.g. YAML frontmatter + # title)
        preamble = parts[0]
        idx = 1
        if idx < len(parts):
            sections.append(preamble + "\n\n" + parts[idx])
            idx += 1
        while idx < len(parts):
            sections.append(parts[idx])
            idx += 1
    else:
        sections = list(parts)

    chunks: List[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= chunk_size:
            chunks.append(section)
        else:
            # Sliding window over paragraphs
            paragraphs = re.split(r'\n\n+', section)
            window: List[str] = []
            window_len = 0
            for para in paragraphs:
                para_len = len(para)
                if window and window_len + para_len > chunk_size:
                    # Flush current window as a chunk
                    chunk = "\n\n".join(window)
                    chunks.append(chunk)
                    # Keep overlap: remove paragraphs from the front until
                    # the remaining text fits within chunk_overlap
                    while window and sum(len(p) for p in window) > chunk_overlap:
                        removed = window.pop(0)
                        window_len -= len(removed)
                window.append(para)
                window_len += para_len
            if window:
                chunk = "\n\n".join(window)
                chunks.append(chunk)

    return chunks


# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

def _make_chunk_id(source: str, chunk_idx: int, text: str) -> str:
    """Produce a stable, collision-resistant chunk ID using MD5.

    Args:
        source: File path or unique identifier for the source document.
        chunk_idx: Zero-based index of the chunk within the document.
        text: The chunk text (included so content changes produce new IDs).

    Returns:
        Hex-encoded MD5 digest string.
    """
    raw = f"{source}::chunk_{chunk_idx}::text={text[:200]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def _extract_frontmatter(text: str) -> Dict[str, str]:
    """Extract YAML frontmatter key-value pairs from markdown text.

    Only handles simple ``key: value`` lines inside ``---`` fences.

    Args:
        text: Full markdown document.

    Returns:
        Dict of extracted key-value pairs.
    """
    fm: Dict[str, str] = {}
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return fm
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, value = line.partition(':')
        fm[key.strip()] = value.strip()
    return fm


def _guess_stock_info(filename: str) -> tuple:
    """Guess stock_code and stock_name from a filename like
    'stockname_600036_financial_summary.md'.

    Args:
        filename: Basename of the markdown file.

    Returns:
        (stock_code, stock_name) tuple.  Either may be empty string.
    """
    stem = Path(filename).stem  # remove .md
    # Pattern: name_XXXXXXXX_financial_summary
    m = re.match(r'(.+?)_(\d{6})_financial_summary$', stem)
    if m:
        return m.group(2), m.group(1)
    return "", ""


# ---------------------------------------------------------------------------
# Public API: ingest markdown files
# ---------------------------------------------------------------------------

def ingest_markdown_files(
    md_dir: str,
    collection_name: str,
    embed_client: Any,
    chroma_client: Any,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> int:
    """Batch-ingest all *_financial_summary.md files from *md_dir* into ChromaDB.

    Args:
        md_dir: Directory containing markdown financial summary files.
        collection_name: ChromaDB collection name (e.g. ``financials``).
        embed_client: An ``EmbeddingClient`` instance (from investment_rag).
        chroma_client: A ``ChromaClient`` instance (from investment_rag).
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Character overlap between consecutive chunks.

    Returns:
        Total number of chunks ingested.
    """
    md_path = Path(md_dir)
    if not md_path.is_dir():
        logger.warning("Markdown directory does not exist: %s", md_dir)
        return 0

    pattern = "*_financial_summary.md"
    files = sorted(md_path.glob(pattern))
    if not files:
        logger.warning("No %s files found in %s", pattern, md_dir)
        return 0

    logger.info("Found %d markdown files in %s", len(files), md_dir)

    all_ids: List[str] = []
    all_texts: List[str] = []
    all_metadatas: List[Dict[str, Any]] = []

    for fpath in files:
        text = fpath.read_text(encoding="utf-8")
        if not text.strip():
            logger.warning("Skipping empty file: %s", fpath.name)
            continue

        stock_code, stock_name = _guess_stock_info(fpath.name)
        fm = _extract_frontmatter(text)
        # Frontmatter overrides if present
        stock_code = fm.get("stock_code", stock_code)
        stock_name = fm.get("stock_name", stock_name)

        chunks = _split_markdown(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        for idx, chunk in enumerate(chunks):
            chunk_id = _make_chunk_id(fpath.name, idx, chunk)
            all_ids.append(chunk_id)
            all_texts.append(chunk)
            all_metadatas.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "source": fpath.name,
                "data_type": "financial_summary",
                "chunk_idx": idx,
            })

        logger.info(
            "File %s: %d chunks (stock=%s, name=%s)",
            fpath.name, len(chunks), stock_code, stock_name,
        )

    if not all_texts:
        return 0

    # Embed in batches (embed_client handles its own internal batching)
    logger.info("Embedding %d chunks ...", len(all_texts))
    all_embeddings = embed_client.embed_texts(all_texts, text_type="document")

    # Store via ChromaClient.add_documents
    collection = chroma_client.get_collection(collection_name)
    # ChromaDB add in batches to respect limits
    batch_size = 5000
    for i in range(0, len(all_texts), batch_size):
        end = min(i + batch_size, len(all_texts))
        collection.add(
            ids=all_ids[i:end],
            documents=all_texts[i:end],
            embeddings=all_embeddings[i:end],
            metadatas=all_metadatas[i:end],
        )

    logger.info(
        "Ingested %d chunks from %d files into collection '%s'",
        len(all_texts), len(files), collection_name,
    )
    return len(all_texts)


# ---------------------------------------------------------------------------
# Public API: ingest PDF extracted text
# ---------------------------------------------------------------------------

def ingest_pdf_text(
    pdf_path: str,
    stock_code: str,
    stock_name: str,
    report_year: str,
    collection_name: str,
    embed_client: Any,
    chroma_client: Any,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> int:
    """Ingest extracted text from a single PDF annual report into ChromaDB.

    The caller is responsible for extracting text from the PDF first (e.g.
    via PyMuPDF / pdfplumber).  This function accepts the *already-extracted*
    plain text and chunks + embeds it.

    Args:
        pdf_path: Path to the PDF file (used as source metadata).
        stock_code: 6-digit stock code.
        stock_name: Stock name.
        report_year: Year of the annual report (e.g. ``2025``).
        collection_name: ChromaDB collection name.
        embed_client: An ``EmbeddingClient`` instance.
        chroma_client: A ``ChromaClient`` instance.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Character overlap between consecutive chunks.

    Returns:
        Number of chunks ingested.
    """
    ppath = Path(pdf_path)
    if not ppath.is_file():
        logger.warning("PDF file does not exist: %s", pdf_path)
        return 0

    text = ppath.read_text(encoding="utf-8") if ppath.suffix != ".pdf" else ""
    # If caller passed a .pdf file directly we cannot read it here; they must
    # pass the extracted text via pdf_path pointing to a .txt file instead.
    if not text.strip():
        logger.warning(
            "No text extracted from %s. "
            "Pass a .txt file with extracted content instead of the raw PDF.",
            pdf_path,
        )
        return 0

    chunks = _split_plain_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if not chunks:
        return 0

    ids: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        chunk_id = _make_chunk_id(ppath.name, idx, chunk)
        ids.append(chunk_id)
        metadatas.append({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "source": ppath.name,
            "data_type": "annual_report",
            "report_year": report_year,
            "chunk_idx": idx,
        })

    logger.info("Embedding %d chunks for %s (%s) ...", len(chunks), stock_name, stock_code)
    embeddings = embed_client.embed_texts(chunks, text_type="document")

    collection = chroma_client.get_collection(collection_name)
    collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    logger.info(
        "Ingested %d chunks from %s into collection '%s'",
        len(chunks), ppath.name, collection_name,
    )
    return len(chunks)
