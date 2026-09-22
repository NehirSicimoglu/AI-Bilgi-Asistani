"""/chat API ucu (uçtan uca, ağsız fake LLM)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_chat_after_upload_returns_answer_and_citations(client: TestClient) -> None:
    data = ("LangChain LLM uygulamaları için bir çatıdır. " * 40).encode()
    up = client.post(
        "/api/v1/documents",
        files={"file": ("langchain.txt", data, "text/plain")},
        data={"category": "framework"},
    )
    assert up.status_code == 201

    resp = client.post("/api/v1/chat", json={"query": "LangChain nedir?", "top_k": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"]
    assert len(body["citations"]) >= 1
    assert body["citations"][0]["document_name"] == "langchain.txt"
    assert "total_tokens" in body["usage"]


def test_chat_empty_query_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/chat", json={"query": ""})
    assert resp.status_code == 422


def test_chat_no_documents_returns_canned(client: TestClient) -> None:
    resp = client.post("/api/v1/chat", json={"query": "hiç doküman yok"})
    assert resp.status_code == 200
    assert "bilgi bulamadım" in resp.json()["answer"].lower()
