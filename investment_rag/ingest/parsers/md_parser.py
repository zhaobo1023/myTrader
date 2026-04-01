# -*- coding: utf-8 -*-
"""
Markdown parser: parse Obsidian-style markdown files into chunks.

Supports:
- Frontmatter extraction (YAML between ---)
- Heading-based section splitting
- Table preservation
- Metadata extraction (tags, title)
"""
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from investment_rag.ingest.parsers.pdf_parser import Chunk, _split_text

logger = logging.getLogger(__name__)


@dataclass
class MarkdownMeta:
    """Extracted metadata from markdown frontmatter."""
    title: str = ""
    tags: List[str] = field(default_factory=list)
    date: str = ""
    sector: str = ""
    raw_frontmatter: Dict = field(default_factory=dict)


def _extract_frontmatter(text: str) -> tuple:
    """Extract YAML frontmatter from markdown text.

    Returns:
        (frontmatter_dict, remaining_text)
    """
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, text, re.DOTALL)

    if not match:
        return {}, text

    frontmatter_str = match.group(1)
    remaining = text[match.end():]

    # Simple YAML parsing (no pyyaml dependency needed)
    fm = {}
    for line in frontmatter_str.split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Handle list values like [tag1, tag2]
        if value.startswith('[') and value.endswith(']'):
            value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(',')]
        fm[key] = value

    return fm, remaining


def _parse_markdown_meta(frontmatter: dict) -> MarkdownMeta:
    """Parse frontmatter dict into MarkdownMeta."""
    tags = frontmatter.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]

    return MarkdownMeta(
        title=frontmatter.get('title', frontmatter.get('name', '')),
        tags=tags,
        date=str(frontmatter.get('date', '')),
        sector=frontmatter.get('sector', ''),
        raw_frontmatter=frontmatter,
    )


def _split_by_headings(text: str, min_chunk_size: int = 200) -> List[str]:
    """Split markdown text by headings (## and above).

    Sections smaller than min_chunk_size are merged with the previous section.
    """
    # Split on ## headings (not # which is usually the title)
    sections = re.split(r'(?=^#{1,3}\s)', text, flags=re.MULTILINE)

    if len(sections) <= 1:
        return [text] if text.strip() else []

    # Merge small sections with previous
    merged = []
    current = ""

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(current) + len(section) < min_chunk_size and current:
            current = current + "\n\n" + section
        else:
            if current:
                merged.append(current)
            current = section

    if current:
        merged.append(current)

    return merged


class MarkdownParser:
    """Parse markdown files into chunks."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse_file(self, md_path: str, source_name: str = "") -> List[Chunk]:
        """Parse a markdown file into chunks.

        Args:
            md_path: Path to the markdown file.
            source_name: Optional source name. Defaults to filename.

        Returns:
            List of Chunk objects.
        """
        if not Path(md_path).exists():
            raise FileNotFoundError(f"Markdown not found: {md_path}")

        if not source_name:
            source_name = Path(md_path).name

        with open(md_path, 'r', encoding='utf-8') as f:
            text = f.read()

        return self.parse_text(text, source_name)

    def parse_text(self, text: str, source_name: str = "") -> List[Chunk]:
        """Parse markdown text into chunks.

        Args:
            text: Raw markdown text.
            source_name: Source identifier for metadata.

        Returns:
            List of Chunk objects.
        """
        if not text.strip():
            return []

        # Extract frontmatter
        frontmatter, body = _extract_frontmatter(text)
        meta = _parse_markdown_meta(frontmatter)

        # Split by headings first
        sections = _split_by_headings(body)

        # Further chunk long sections
        chunks = []
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
                        metadata={
                            "title": meta.title,
                            "tags": meta.tags,
                            "date": meta.date,
                            "sector": meta.sector,
                        },
                    ))
                continue

            if chunk_text:
                chunk_id = f"{source_name}_s{section_idx}_c{len(chunks)}"
                chunks.append(Chunk(
                    text=chunk_text,
                    source=source_name,
                    page=0,
                    chunk_id=chunk_id,
                    metadata={
                        "title": meta.title,
                        "tags": meta.tags,
                        "date": meta.date,
                        "sector": meta.sector,
                    },
                ))

        logger.info("Parsed %d chunks from %s", len(chunks), source_name)
        return chunks
