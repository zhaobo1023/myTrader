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
        client = TestClient(app)
        resp = client.post("/ingest", json={"paths": [], "collection": "reports"})
        assert resp.status_code == 200
        data = resp.json()
        # Empty paths should return no_chunks
        assert data["status"] == "no_chunks"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
