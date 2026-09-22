"""/metrics ucu ve alan metriklerinin toplanması, ağsız. Hafif kapsam."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_metrics_endpoint_exposes_prometheus(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    # Tanımlı metrik aileleri çıktı formatında görünmeli.
    assert "rag_http_requests_total" in body
    assert "rag_chat_seconds" in body
    assert "rag_retrieval_seconds" in body


def test_request_id_header_present(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")


def test_chat_and_ingestion_update_metrics(client: TestClient) -> None:
    data = ("Prometheus metrik toplar. " * 40).encode()
    client.post(
        "/api/v1/documents",
        files={"file": ("obs.txt", data, "text/plain")},
        data={"category": "ops"},
    )
    client.post("/api/v1/chat", json={"query": "metrik nedir?", "top_k": 3})

    body = client.get("/metrics").text
    # İndeksleme ve chat metrikleri artmış olmalı (0 sayımlar da satır olarak görünür).
    assert "rag_documents_ingested_total" in body
    assert "rag_chunks_indexed_total" in body
    assert "rag_chat_seconds_count" in body
