# -*- coding: utf-8 -*-
"""
Annual report PDF download, text extraction, and ChromaDB ingest.

Flow:
  1. Query ChromaDB: if recent annual report already ingested -> skip
  2. Search cninfo for annual report PDFs (last 3 years)
  3. Download PDF to temp file
  4. Extract text with PyMuPDF
  5. Smart-chunk text, embed, upsert into ChromaDB collection 'annual_reports'

All operations are idempotent (chunk IDs are content-hash based).
"""

import hashlib
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import requests

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "annual_reports"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

# Key sections to prioritize in annual reports
_KEY_SECTION_PATTERNS = [
    r"管理层讨论与分析",
    r"经营情况讨论与分析",
    r"主要财务数据",
    r"核心竞争力",
    r"业务概要",
    r"主要业务",
    r"主营业务",
    r"风险因素",
    r"重大风险",
    r"未来展望",
    r"发展战略",
    r"现金流",
    r"资本支出",
    r"在建工程",
    r"新签订单",
    r"船队",
    r"交付",
]

_CNINFO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
    "Origin": "https://www.cninfo.com.cn",
}


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------

def _get_chroma_collection():
    from investment_rag.config import load_config
    from investment_rag.store.chroma_client import ChromaClient
    cfg = load_config()
    client = ChromaClient(config=cfg)
    return client.get_collection(COLLECTION_NAME)


def _already_ingested(stock_code: str, report_year: str) -> bool:
    """Return True if this stock+year is already in ChromaDB."""
    try:
        col = _get_chroma_collection()
        results = col.get(
            where={"$and": [
                {"stock_code": {"$eq": stock_code}},
                {"report_year": {"$eq": report_year}},
            ]},
            limit=1,
        )
        return bool(results and results.get("ids"))
    except Exception as e:
        logger.warning("[ingest] _already_ingested check failed: %s", e)
        return False


def _years_needed(stock_code: str, years: int = 3) -> List[str]:
    """Return list of year strings not yet ingested."""
    current_year = date.today().year
    # Include current year only if we're past March (annual report season)
    if date.today().month >= 4:
        start_year = current_year
    else:
        start_year = current_year - 1
    needed = []
    for y in range(start_year, start_year - years, -1):
        yr = str(y)
        if not _already_ingested(stock_code, yr):
            needed.append(yr)
    return needed


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

def _search_annual_reports(stock_code: str, stock_name: str,
                            start_year: int) -> List[Dict]:
    """Search cninfo for annual report PDFs."""
    start_date = f"{start_year}-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    url = "https://www.cninfo.com.cn/new/fulltextSearch/full"
    payload = {
        "searchkey": f"{stock_code} 年度报告",
        "sdate": start_date,
        "edate": end_date,
        "isfulltext": "false",
        "sortName": "pubdate",
        "sortType": "desc",
        "pageNum": "1",
        "pageSize": "20",
    }

    results = []
    try:
        resp = requests.post(url, data=payload, headers=_CNINFO_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for ann in (data.get("announcements") or []):
            if ann.get("secCode") != stock_code:
                continue
            title = ann.get("announcementTitle", "").replace("<em>", "").replace("</em>", "")
            if any(kw in title for kw in ["摘要", "英文", "补充", "更正", "说明", "督导"]):
                continue
            if "年度报告" not in title or "半年度报告" in title:
                continue
            adjunct_url = ann.get("adjunctUrl", "")
            if not adjunct_url:
                continue

            ann_time = ann.get("announcementTime", 0)
            date_str = datetime.fromtimestamp(ann_time / 1000).strftime("%Y-%m-%d") if ann_time else ""
            year_match = re.search(r"(20\d{2})", title)
            report_year = year_match.group(1) if year_match else date_str[:4]

            results.append({
                "title": title,
                "date": date_str,
                "report_year": report_year,
                "url": f"http://static.cninfo.com.cn/{adjunct_url}",
                "code": stock_code,
                "name": stock_name,
            })
        logger.info("[ingest] %s search: %d annual reports found", stock_code, len(results))
    except Exception as e:
        logger.error("[ingest] cninfo search failed for %s: %s", stock_code, e)

    return results


def _download_pdf_to_temp(url: str) -> Optional[str]:
    """Download PDF URL to a temp file. Returns temp file path or None."""
    try:
        resp = requests.get(url, headers=_CNINFO_HEADERS, timeout=120, stream=True)
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        for chunk in resp.iter_content(chunk_size=65536):
            tmp.write(chunk)
        tmp.close()
        size_mb = os.path.getsize(tmp.name) / 1024 / 1024
        logger.info("[ingest] downloaded %.1f MB to %s", size_mb, tmp.name)
        return tmp.name
    except Exception as e:
        logger.error("[ingest] PDF download failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_text_pymupdf(pdf_path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = []
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                pages.append(text)
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        logger.error("[ingest] PyMuPDF extraction failed: %s", e)
        return ""


def _is_key_section(text: str) -> bool:
    """Return True if text chunk contains a key section keyword."""
    for pat in _KEY_SECTION_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def _smart_chunk(text: str, stock_name: str) -> List[str]:
    """
    Split annual report text into chunks.
    - Remove boilerplate (table of contents markers, page footers)
    - Split on paragraph boundaries
    - Prioritize chunks with key financial/business content
    """
    # Remove common boilerplate patterns
    text = re.sub(r'[-=]{20,}', '', text)
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)  # standalone page numbers
    text = re.sub(r'[ \t]{4,}', '  ', text)        # excessive whitespace

    paragraphs = re.split(r'\n{2,}', text)
    paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 30]

    chunks: List[str] = []
    window: List[str] = []
    window_len = 0

    for para in paragraphs:
        para_len = len(para)
        if window and window_len + para_len > CHUNK_SIZE:
            chunk_text = "\n\n".join(window)
            chunks.append(chunk_text)
            # Keep overlap
            while window and sum(len(p) for p in window) > CHUNK_OVERLAP:
                removed = window.pop(0)
                window_len -= len(removed)
        window.append(para)
        window_len += para_len

    if window:
        chunks.append("\n\n".join(window))

    return chunks


# ---------------------------------------------------------------------------
# Embedding + upsert
# ---------------------------------------------------------------------------

def _make_chunk_id(stock_code: str, report_year: str, idx: int, text: str) -> str:
    raw = f"annual_report::{stock_code}::{report_year}::chunk_{idx}::{text[:100]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _embed_and_upsert(
    chunks: List[str],
    stock_code: str,
    stock_name: str,
    report_year: str,
    source_title: str,
) -> int:
    """Embed chunks and upsert into ChromaDB. Returns number of chunks stored."""
    if not chunks:
        return 0

    from investment_rag.config import load_config
    from investment_rag.embeddings.embed_model import EmbeddingClient
    from investment_rag.store.chroma_client import ChromaClient

    cfg = load_config()
    embed_client = EmbeddingClient(config=cfg)
    chroma_client = ChromaClient(config=cfg)
    collection = chroma_client.get_collection(COLLECTION_NAME)

    ids = []
    metadatas = []
    for idx, chunk in enumerate(chunks):
        ids.append(_make_chunk_id(stock_code, report_year, idx, chunk))
        metadatas.append({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_year": report_year,
            "source": source_title,
            "data_type": "annual_report",
            "is_key_section": str(_is_key_section(chunk)).lower(),
            "chunk_idx": idx,
        })

    logger.info("[ingest] embedding %d chunks for %s %s ...", len(chunks), stock_name, report_year)
    # Embed in batches of 10 (API limit)
    all_embeddings = embed_client.embed_texts(chunks, text_type="document")

    # Upsert in batches of 500
    batch_size = 500
    for i in range(0, len(chunks), batch_size):
        end = min(i + batch_size, len(chunks))
        collection.upsert(
            ids=ids[i:end],
            documents=chunks[i:end],
            embeddings=all_embeddings[i:end],
            metadatas=metadatas[i:end],
        )

    logger.info("[ingest] stored %d chunks for %s %s", len(chunks), stock_name, report_year)
    return len(chunks)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_annual_reports(
    stock_code: str,
    stock_name: str,
    years: int = 3,
) -> Dict[str, Any]:
    """
    Main entry: download and ingest annual reports for a stock.

    Args:
        stock_code: 6-digit bare code (e.g. '601872')
        stock_name: Display name
        years: How many years back to cover (default 3)

    Returns:
        {ingested: {year: chunk_count}, skipped: [year], errors: [year]}
    """
    bare = stock_code.split(".")[0] if "." in stock_code else stock_code

    needed_years = _years_needed(bare, years=years)
    if not needed_years:
        logger.info("[ingest] %s: all %d years already in ChromaDB, skipping", bare, years)
        return {"ingested": {}, "skipped": [], "errors": []}

    current_year = date.today().year
    start_year = current_year - years
    anns = _search_annual_reports(bare, stock_name, start_year)

    # Deduplicate: keep latest PDF per year
    year_to_ann: Dict[str, Dict] = {}
    for ann in anns:
        yr = ann["report_year"]
        if yr in needed_years and yr not in year_to_ann:
            year_to_ann[yr] = ann

    result = {"ingested": {}, "skipped": [], "errors": []}

    for yr, ann in sorted(year_to_ann.items(), reverse=True):
        pdf_path = None
        try:
            logger.info("[ingest] processing %s %s: %s", bare, yr, ann["title"])
            pdf_path = _download_pdf_to_temp(ann["url"])
            if not pdf_path:
                result["errors"].append(yr)
                continue

            text = _extract_text_pymupdf(pdf_path)
            if not text.strip():
                logger.warning("[ingest] no text extracted from %s %s", bare, yr)
                result["errors"].append(yr)
                continue

            logger.info("[ingest] extracted %d chars from %s %s", len(text), bare, yr)
            chunks = _smart_chunk(text, stock_name)
            logger.info("[ingest] %d chunks for %s %s", len(chunks), bare, yr)

            n = _embed_and_upsert(chunks, bare, stock_name, yr, ann["title"])
            result["ingested"][yr] = n
            time.sleep(1.0)

        except Exception as e:
            logger.error("[ingest] failed for %s %s: %s", bare, yr, e)
            result["errors"].append(yr)
        finally:
            if pdf_path and os.path.exists(pdf_path):
                os.unlink(pdf_path)

    logger.info(
        "[ingest] %s done: ingested=%s skipped=%s errors=%s",
        bare, result["ingested"], result["skipped"], result["errors"],
    )
    return result
