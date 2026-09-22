"""Konuşma API'si + çok turlu sohbetin uçtan uca kalıcılığı (ağsız).

`client` fixture'ı StaticPool kullandığından DB istekler arası paylaşılır; bu da
kalıcılığı gerçekten doğrular.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_conversation_crud(client: TestClient) -> None:
    created = client.post("/api/v1/conversations", json={"title": "Sohbet"})
    assert created.status_code == 201, created.text
    cid = created.json()["id"]

    listed = client.get("/api/v1/conversations")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    detail = client.get(f"/api/v1/conversations/{cid}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Sohbet"
    assert detail.json()["messages"] == []

    deleted = client.delete(f"/api/v1/conversations/{cid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/conversations/{cid}").status_code == 404


def test_get_unknown_conversation_404(client: TestClient) -> None:
    assert client.get("/api/v1/conversations/yoktur").status_code == 404


def test_rename_conversation(client: TestClient) -> None:
    created = client.post("/api/v1/conversations", json={})
    cid = created.json()["id"]

    renamed = client.patch(f"/api/v1/conversations/{cid}", json={"title": "Qdrant nedir?"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Qdrant nedir?"
    assert client.get(f"/api/v1/conversations/{cid}").json()["title"] == "Qdrant nedir?"

    assert client.patch("/api/v1/conversations/yoktur", json={"title": "x"}).status_code == 404


def test_chat_with_conversation_persists_history(client: TestClient) -> None:
    data = ("LangChain LLM uygulamaları için bir çatıdır. " * 40).encode()
    up = client.post(
        "/api/v1/documents",
        files={"file": ("langchain.txt", data, "text/plain")},
        data={"category": "framework"},
    )
    assert up.status_code == 201

    cid = client.post("/api/v1/conversations", json={}).json()["id"]

    resp = client.post(
        "/api/v1/chat",
        json={"query": "LangChain nedir?", "top_k": 3, "conversation_id": cid},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["conversation_id"] == cid

    detail = client.get(f"/api/v1/conversations/{cid}").json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["content"] == "LangChain nedir?"
    assert detail["messages"][1]["role"] == "assistant"
    assert len(detail["messages"][1]["citations"]) >= 1


def test_chat_unknown_conversation_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/chat",
        json={"query": "merhaba", "conversation_id": "yoktur"},
    )
    assert resp.status_code == 404
