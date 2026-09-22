"""Altyapı: request-id middleware ve exception handler'lar."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.exceptions import NotFoundError, register_exception_handlers
from app.main import create_app
from app.observability import REQUEST_ID_HEADER


def test_request_id_header_present() -> None:
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get(REQUEST_ID_HEADER)


def test_incoming_request_id_is_echoed() -> None:
    client = TestClient(create_app())
    resp = client.get("/health", headers={REQUEST_ID_HEADER: "abc123"})
    assert resp.headers.get(REQUEST_ID_HEADER) == "abc123"


def test_app_error_maps_to_status() -> None:
    app = create_app()
    register_exception_handlers(app)

    @app.get("/_boom")
    async def _boom():
        raise NotFoundError("bulunamadı")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/_boom")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "bulunamadı"
