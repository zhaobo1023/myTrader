# -*- coding: utf-8 -*-
"""
Word document parser: extract text from .docx files using python-docx.

Splits by heading paragraphs (Heading 1-3), then further chunks
long sections using the same _split_text from pdf_parser.

Usage:
    from investment_rag.ingest.parsers.docx_parser import DocxParser
    parser = DocxParser(chunk_size=800, chunk_overlap=150)
    chunks = parser.parse_file("report.docx")
"""
import re
import logging
from pathlib import Path
from typing import List

from docx import Document

from investment_rag.ingest.parsers.pdf_parser import Chunk, _split_text

logger = logging.getLogger(__name__)

# Styles that represent headings in python-docx
HEADING_STYLES = {'Heading 1', 'Heading 2', 'Heading 3', 'heading 1',
                  'heading 2', 'heading 3', 'Title'}


def _is_heading(paragraph) -> bool:
    """Check if a paragraph is a heading."""
    style_name = paragraph.style.name if paragraph.style else ''
    return style_name in HEADING_STYLES


def _split_by_headings(doc: Document, min_chunk_size: int = 200) -> List[str]:
    """Split document text by heading paragraphs.

    Each heading starts a new section. Sections smaller than
    min_chunk_size are merged with the previous section.
    """
    sections: List[str] = []
    current_lines: List[str] = []
    current_title = ""

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        if _is_heading(para):
            # Flush current section
            if current_lines:
                section_text = '\n'.join(current_lines).strip()
                if section_text:
                    sections.append(section_text)
            current_lines = [text]
        else:
            current_lines.append(text)

    # Flush last section
    if current_lines:
        section_text = '\n'.join(current_lines).strip()
        if section_text:
            sections.append(section_text)

    if not sections:
        return []

    # Merge small sections with previous
    merged: List[str] = []
    current = ""

    for section in sections:
        if len(current) + len(section) < min_chunk_size and current:
            current = current + "\n\n" + section
        else:
            if current:
                merged.append(current)
            current = section

    if current:
        merged.append(current)

    return merged


class DocxParser:
    """Parse Word .docx files into chunks."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse_file(self, docx_path: str, source_name: str = "") -> List[Chunk]:
        """Parse a .docx file into chunks.

        Args:
            docx_path: Path to the .docx file.
            source_name: Optional source name. Defaults to filename.

        Returns:
            List of Chunk objects.
        """
        if not Path(docx_path).exists():
            raise FileNotFoundError(f"Word document not found: {docx_path}")

        if not source_name:
            source_name = Path(docx_path).name

        doc = Document(docx_path)
        sections = _split_by_headings(doc)

        chunks: List[Chunk] = []
        for section_idx, section in enumerate(sections):
            if len(section) <= self.chunk_size:
                chunk_text = section.strip()
            else:
                sub_chunks = _split_text(section, self.chunk_size, self.chunk_overlap)
                for sub in sub_chunks:
                    chunk_id = f"{source_name}_s{section_idx}_c{len(chunks)}"
                    chunks.append(Chunk(
                        text=sub.strip(),
                        source=source_name,
                        page=0,
                        chunk_id=chunk_id,
                        metadata={},
                    ))
                continue

            if chunk_text:
                chunk_id = f"{source_name}_s{section_idx}_c{len(chunks)}"
                chunks.append(Chunk(
                    text=chunk_text,
                    source=source_name,
                    page=0,
                    chunk_id=chunk_id,
                    metadata={},
                ))

        logger.info("Parsed %d chunks from %s", len(chunks), source_name)
        return chunks
