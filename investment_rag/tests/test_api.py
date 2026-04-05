# -*- coding: utf-8 -*-
"""Integration test for FastAPI /query endpoint."""
import pytest
from fastapi.testclient import TestClient


class TestAPI:
    """Tests for the FastAPI endpoints."""

    def test_health_endpoint(self):
        from investment_rag.api.main import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "error")

    def test_query_endpoint_validation(self):
        from investment_rag.api.main import app
        client = TestClient(app)
        # Empty query should fail validation
        resp = client.post("/query", json={"query": ""})
        assert resp.status_code == 422

    def test_query_endpoint_missing_field(self):
        from investment_rag.api.main import app
        client = TestClient(app)
        resp = client.post("/query", json={})
        assert resp.status_code == 422

    def test_ingest_endpoint_validation(self):
        from investment_rag.api.main import app
        from unittest.mock import patch, MagicMock
        import sys
        client = TestClient(app)
        # The ingest handler lazily imports IngestPipeline; its transitive import chain
        # requires rank_bm25 which is not installed in this dev environment.
        # Stub the entire module in sys.modules so the import resolves without error.
        mock_result = {"status": "no_chunks", "files_processed": 0, "chunks_created": 0, "errors": []}
        mock_module = MagicMock()
        mock_module.IngestPipeline.return_value.ingest_paths.return_value = mock_result
        with patch.dict(sys.modules, {"investment_rag.ingest.ingest_pipeline": mock_module}):
            resp = client.post("/ingest", json={"paths": [], "collection": "reports"})
        assert resp.status_code == 200
        data = resp.json()
        # Empty paths should return no_chunks
        assert data["status"] == "no_chunks"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
