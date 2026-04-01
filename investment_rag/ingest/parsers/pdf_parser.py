# -*- coding: utf-8 -*-
"""
PDF parser: extract text from PDF files using PyMuPDF, then chunk.

Usage:
    from investment_rag.ingest.parsers.pdf_parser import PDFParser
    parser = PDFParser(chunk_size=800, chunk_overlap=150)
    chunks = parser.parse_file("report.pdf")
"""
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A text chunk with metadata."""
    text: str
    source: str
    page: int
    chunk_id: str
    metadata: dict = field(default_factory=dict)


def _split_text(text: str, chunk_size: int = 800, chunk_overlap: int = 150) -> List[str]:
    """Split text into overlapping chunks, respecting Chinese paragraph boundaries."""
    if not text or not text.strip():
        return []

    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    # Split on paragraph boundaries first
    paragraphs = re.split(r'\n\n+', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # If a single paragraph exceeds chunk_size, split it further by sentences
        if len(para) > chunk_size:
            # Flush current chunk first
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # Split long paragraph by Chinese/English sentence boundaries
            sentences = re.split(r'(?<=[。！？\.\!\?])', para)
            sentences = [s.strip() for s in sentences if s.strip()]

            # If no sentence boundaries found, split by character count
            if len(sentences) <= 1:
                _split_long_text(para, chunk_size, chunk_overlap, chunks)
                continue

            for sent in sentences:
                if len(current_chunk) + len(sent) + 1 > chunk_size and current_chunk:
                    chunks.append(current_chunk)
                    # Keep overlap from end of previous chunk
                    if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                        current_chunk = current_chunk[-chunk_overlap:] + " " + sent
                    else:
                        current_chunk = sent
                else:
                    current_chunk = current_chunk + " " + sent if current_chunk else sent
        elif len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            chunks.append(current_chunk)
            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                current_chunk = current_chunk[-chunk_overlap:] + "\n\n" + para
            else:
                current_chunk = para
        else:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _split_long_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    chunks: list,
) -> None:
    """Split a long text without sentence boundaries into fixed-size chunks with overlap."""
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start = end - chunk_overlap


class PDFParser:
    """Parse PDF files and chunk the extracted text."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_text(self, pdf_path: str) -> List[str]:
        """Extract text from each page of a PDF file.

        Returns:
            List of page texts (one entry per page).
        """
        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(pdf_path)
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            pages.append(text)

        doc.close()
        logger.info("Extracted %d pages from %s", len(pages), pdf_path)
        return pages

    def parse_file(self, pdf_path: str, source_name: str = "") -> List[Chunk]:
        """Parse a PDF file into chunks.

        Args:
            pdf_path: Path to the PDF file.
            source_name: Optional source name for metadata. Defaults to filename.

        Returns:
            List of Chunk objects.
        """
        if not source_name:
            source_name = Path(pdf_path).name

        pages = self.extract_text(pdf_path)
        chunks = []

        for page_idx, page_text in enumerate(pages):
            if not page_text.strip():
                continue

            raw_chunks = _split_text(page_text, self.chunk_size, self.chunk_overlap)
            for chunk_idx, chunk_text in enumerate(raw_chunks):
                chunk_id = f"{source_name}_p{page_idx + 1}_c{chunk_idx}"
                chunks.append(Chunk(
                    text=chunk_text.strip(),
                    source=source_name,
                    page=page_idx + 1,
                    chunk_id=chunk_id,
                ))

        logger.info("Parsed %d chunks from %s", len(chunks), pdf_path)
        return chunks
