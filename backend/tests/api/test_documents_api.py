"""/documents API uçları (uçtan uca, ağsız). `client` fixture'ı conftest'te."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_upload_list_get_delete_flow(client: TestClient) -> None:
    # Yükle
    data = ("FastAPI modern bir Python web çatısıdır. " * 40).encode()
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("fastapi.txt", data, "text/plain")},
        data={"category": "framework"},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["status"] == "indexed"
    assert doc["num_chunks"] > 0
    assert doc["category"] == "framework"
    doc_id = doc["id"]

    # Listele
    resp = client.get("/api/v1/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == doc_id

    # Tek doküman
    resp = client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["filename"] == "fastapi.txt"

    # Sil
    resp = client.delete(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 204

    # Silindi
    resp = client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 404


def test_unsupported_type_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("kurulum.exe", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unsupported_file_type"


def test_corrupt_file_returns_422(client: TestClient) -> None:
    """Uzantısı desteklenen ama içeriği bozuk dosya 500 değil 422 dönmeli."""
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("bozuk.xlsx", b"gecerli bir xlsx degil", "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "corrupt_file"
