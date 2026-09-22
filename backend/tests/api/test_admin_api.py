"""/admin/stats API ucu (ağsız)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_stats_reflects_uploaded_documents(client: TestClient) -> None:
    data = ("Qdrant bir vektör veritabanıdır. " * 40).encode()
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("qdrant.txt", data, "text/plain")},
        data={"category": "databases"},
    )
    assert resp.status_code == 201, resp.text

    resp = client.get("/api/v1/admin/stats")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["documents_total"] == 1
    assert body["documents_by_status"] == {"indexed": 1}
    assert body["chunks_indexed"] > 0
    assert body["conversations_total"] == 0
    assert body["chat_requests_total"] >= 0
    assert body["total_llm_tokens"] >= 0


def test_admin_stats_empty_system(client: TestClient) -> None:
    resp = client.get("/api/v1/admin/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["documents_total"] == 0
    assert body["documents_by_status"] == {}
    assert body["avg_chat_latency_ms"] is None
