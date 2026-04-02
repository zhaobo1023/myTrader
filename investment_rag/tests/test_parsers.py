# -*- coding: utf-8 -*-
"""Unit tests for PDF parser and MD parser."""
import pytest
import os
import tempfile
from investment_rag.ingest.parsers.pdf_parser import PDFParser, Chunk, _split_text
from investment_rag.ingest.parsers.md_parser import (
    MarkdownParser,
    _extract_frontmatter,
    _parse_markdown_meta,
    _split_by_headings,
)


# ============================================================
# _split_text tests
# ============================================================
class TestSplitText:
    def test_empty_string(self):
        assert _split_text("") == []
        assert _split_text("   \n\n  ") == []

    def test_short_text_no_split(self):
        text = "This is a short text."
        result = _split_text(text, chunk_size=800)
        assert len(result) == 1
        assert result[0] == text

    def test_paragraph_split(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = _split_text(text, chunk_size=30, chunk_overlap=5)
        assert len(result) >= 1
        for chunk in result:
            assert len(chunk) <= 35  # allow slight overrun

    def test_overlap(self):
        text = "Word " * 200  # 1000 chars
        result = _split_text(text, chunk_size=100, chunk_overlap=20)
        assert len(result) > 1
        # Check overlap exists between consecutive chunks
        if len(result) >= 2:
            end_of_first = result[0][-20:]
            start_of_second = result[1][:20]
            # They should share some text
            assert end_of_first in result[1] or start_of_second in result[0]

    def test_chinese_paragraphs(self):
        text = "第一段内容。包含一些中文。继续写更多内容。\n\n第二段是独立的。有不同的主题。也有一些额外的文字。"
        result = _split_text(text, chunk_size=50, chunk_overlap=10)
        assert len(result) >= 1
        for chunk in result:
            assert len(chunk) > 0


# ============================================================
# PDFParser tests
# ============================================================
class TestPDFParser:
    def test_file_not_found(self):
        parser = PDFParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/file.pdf")

    def test_parse_real_pdf(self):
        pdf_path = os.path.expanduser(
            "~/Documents/notes/Finance/Research/01-Sectors/化工/化工新材料调研.pdf"
        )
        if not os.path.exists(pdf_path):
            pytest.skip("Test PDF not available")

        parser = PDFParser(chunk_size=500, chunk_overlap=50)
        chunks = parser.parse_file(pdf_path)

        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert len(chunk.text) > 0
            assert chunk.page > 0
            assert chunk.source == "化工新材料调研.pdf"
            assert "化工新材料调研.pdf_p" in chunk.chunk_id

    def test_extract_text(self):
        pdf_path = os.path.expanduser(
            "~/Documents/notes/Finance/Research/01-Sectors/化工/化工新材料调研.pdf"
        )
        if not os.path.exists(pdf_path):
            pytest.skip("Test PDF not available")

        parser = PDFParser()
        pages = parser.extract_text(pdf_path)
        assert len(pages) > 0
        # The PDF has 7 pages
        assert len(pages) <= 10


# ============================================================
# MarkdownParser tests
# ============================================================
class TestMarkdownParser:
    def test_file_not_found(self):
        parser = MarkdownParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/file.md")

    def test_parse_simple_md(self):
        parser = MarkdownParser(chunk_size=500, chunk_overlap=50)
        md_text = """---
title: Test Report
tags: [test, finance]
date: 2026-01-01
---

# Main Title

This is the introduction paragraph.

## Section 1

Content of section 1 with some detail.

## Section 2

Content of section 2 with more detail.
"""
        chunks = parser.parse_text(md_text, "test.md")
        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk.text) > 0
            assert chunk.source == "test.md"
            assert chunk.metadata.get("title") == "Test Report"
            assert "test" in chunk.metadata.get("tags", [])

    def test_parse_empty_md(self):
        parser = MarkdownParser()
        chunks = parser.parse_text("", "empty.md")
        assert chunks == []

    def test_frontmatter_extraction(self):
        text = """---
title: My Report
tags: [a, b, c]
date: 2026-03-01
---

Content here."""
        fm, body = _extract_frontmatter(text)
        assert fm["title"] == "My Report"
        assert fm["tags"] == ["a", "b", "c"]
        assert fm["date"] == "2026-03-01"
        assert "Content here" in body
        assert "---" not in body

    def test_no_frontmatter(self):
        text = "Just plain markdown\n\n## Heading\nContent"
        fm, body = _extract_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_heading_split(self):
        text = "## H2-1\nContent 1\n\n## H2-2\nContent 2\n\n### H3\nContent 3"
        sections = _split_by_headings(text, min_chunk_size=10)
        assert len(sections) >= 2

    def test_parse_real_md(self):
        md_dir = os.path.expanduser(
            "~/Documents/notes/Finance/Research/01-Sectors/煤炭"
        )
        if not os.path.isdir(md_dir):
            pytest.skip("Test MD directory not available")

        md_files = [f for f in os.listdir(md_dir) if f.endswith('.md')]
        if not md_files:
            pytest.skip("No .md files found")

        parser = MarkdownParser(chunk_size=500, chunk_overlap=50)
        md_path = os.path.join(md_dir, md_files[0])
        chunks = parser.parse_file(md_path)
        assert len(chunks) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
