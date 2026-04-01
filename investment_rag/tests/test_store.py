# -*- coding: utf-8 -*-
"""Unit tests for ChromaDB client and BM25 retriever."""
import os
import tempfile
import pytest

from investment_rag.config import RAGConfig
from investment_rag.store.chroma_client import ChromaClient
from investment_rag.retrieval.bm25_retriever import BM25Retriever
from investment_rag.retrieval.hybrid_retriever import rrf_merge


# ============================================================
# ChromaDB client tests
# ============================================================
class TestChromaClient:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        config = RAGConfig(chroma_persist_dir=self.tmpdir)
        self.client = ChromaClient(config)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_collection(self):
        col = self.client.get_collection("test_col")
        assert col is not None
        assert "test_col" in self.client.list_collections()

    def test_add_and_query(self):
        # Add documents
        ids = ["doc1", "doc2", "doc3"]
        texts = ["coal industry analysis", "chemical sector overview", "tech stocks report"]
        embeddings = [
            [0.1] * self.client.dimensions,
            [0.2] * self.client.dimensions,
            [0.3] * self.client.dimensions,
        ]

        self.client.add_documents("test_q", ids, texts, embeddings)
        assert self.client.collection_count("test_q") == 3

        # Query
        query_vec = [0.15] * self.client.dimensions
        results = self.client.query("test_q", query_vec, top_k=2)
        assert len(results) == 2
        assert results[0]["id"] in ids

    def test_empty_query(self):
        col = self.client.get_collection("empty_col")
        assert self.client.collection_count("empty_col") == 0

    def test_delete_collection(self):
        self.client.get_collection("to_delete")
        self.client.delete_collection("to_delete")
        assert "to_delete" not in self.client.list_collections()

    def test_add_with_metadata(self):
        ids = ["m1"]
        texts = ["test doc"]
        embeddings = [[0.1] * self.client.dimensions]
        metadatas = [{"source": "test.pdf", "page": 1}]

        self.client.add_documents("meta_test", ids, texts, embeddings, metadatas)
        query_vec = [0.1] * self.client.dimensions
        results = self.client.query("meta_test", query_vec, top_k=1)
        assert len(results) == 1
        assert results[0]["metadata"]["source"] == "test.pdf"


# ============================================================
# BM25 retriever tests
# ============================================================
class TestBM25Retriever:
    def setup_method(self):
        self.retriever = BM25Retriever()

    def test_build_and_search(self):
        docs = [
            {"id": "1", "text": "煤炭行业深度分析报告"},
            {"id": "2", "text": "化工行业前景展望"},
            {"id": "3", "text": "煤炭价格走势与供需分析"},
        ]
        self.retriever.build_index("test", docs)
        assert self.retriever.has_index("test")

        results = self.retriever.search("test", "煤炭价格", top_k=2)
        assert len(results) > 0
        # The most relevant should be about coal pricing
        assert results[0]["id"] == "3"

    def test_search_no_index(self):
        results = self.retriever.search("nonexistent", "test", top_k=5)
        assert results == []

    def test_build_empty(self):
        self.retriever.build_index("empty", [])
        assert not self.retriever.has_index("empty")


# ============================================================
# RRF merge tests
# ============================================================
class TestRRFMerge:
    def test_merge_both_empty(self):
        assert rrf_merge([], []) == []

    def test_merge_only_dense(self):
        dense = [
            {"id": "a", "text": "doc a"},
            {"id": "b", "text": "doc b"},
        ]
        results = rrf_merge(dense, [], top_k=5)
        assert len(results) == 2

    def test_merge_overlap(self):
        dense = [
            {"id": "a", "text": "doc a"},
            {"id": "b", "text": "doc b"},
        ]
        bm25 = [
            {"id": "b", "text": "doc b"},
            {"id": "c", "text": "doc c"},
        ]
        results = rrf_merge(dense, bm25, top_k=5)
        ids = [r["id"] for r in results]
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids
        # 'b' should be ranked higher (appears in both)
        assert ids.index("b") < ids.index("a")
        assert ids.index("b") < ids.index("c")

    def test_top_k_limit(self):
        dense = [{"id": f"d{i}", "text": f"doc {i}"} for i in range(10)]
        bm25 = [{"id": f"b{i}", "text": f"doc {i}"} for i in range(10)]
        results = rrf_merge(dense, bm25, top_k=3)
        assert len(results) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
