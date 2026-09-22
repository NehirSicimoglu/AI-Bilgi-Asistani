"""/projects API uçları ve proje-sohbet ilişkisi (uçtan uca, ağsız)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_project_crud(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Araştırma"})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["name"] == "Araştırma"

    listed = client.get("/api/v1/projects")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == pid

    renamed = client.patch(f"/api/v1/projects/{pid}", json={"name": "Tez"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Tez"

    assert client.delete(f"/api/v1/projects/{pid}").status_code == 204
    assert client.get("/api/v1/projects").json()["total"] == 0


def test_missing_project_returns_404(client: TestClient) -> None:
    assert client.patch("/api/v1/projects/yok", json={"name": "X"}).status_code == 404
    assert client.delete("/api/v1/projects/yok").status_code == 404


def test_deleting_project_keeps_its_conversations(client: TestClient) -> None:
    """Proje silinince içindeki sohbetler silinmez, yalnızca projeden çıkar.

    `ConversationRow.project_id` ON DELETE SET NULL ile tanımlıdır; kullanıcının
    klasörü silmesi sohbet geçmişini kaybettirmemelidir.
    """
    pid = client.post("/api/v1/projects", json={"name": "Klasör"}).json()["id"]
    cid = client.post("/api/v1/conversations", json={"title": "Sohbet"}).json()["id"]

    moved = client.patch(f"/api/v1/conversations/{cid}", json={"project_id": pid})
    assert moved.status_code == 200
    assert moved.json()["project_id"] == pid

    assert client.delete(f"/api/v1/projects/{pid}").status_code == 204

    survived = client.get(f"/api/v1/conversations/{cid}")
    assert survived.status_code == 200, "proje silindi diye sohbet de silinmemeli"
    assert client.get("/api/v1/conversations").json()["total"] == 1
