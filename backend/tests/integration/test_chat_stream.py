"""Streaming chat (SSE): servis event sırası + SSE formatı + /chat/stream ucu.

Ağsız: fake embedding + FakeLLM (parça parça yield eder) + in-memory Qdrant/SQLite.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.sse import format_sse, sse_stream
from app.ingestion.sparse import Bm25SparseEncoder
from app.services.chat import ChatService, StreamEvent
from app.services.prompts import NO_CONTEXT_ANSWER
from app.services.retrieval import RetrievalService
from tests.conftest import FakeLLM


async def _collect(events) -> list[StreamEvent]:
    return [ev async for ev in events]


# --- SSE formatlama (birim) ---


def test_format_sse_wire_format() -> None:
    wire = format_sse(StreamEvent(event="token", data={"text": "merhaba"}))
    assert wire == 'event: token\ndata: {"text": "merhaba"}\n\n'


def test_format_sse_keeps_turkish_chars() -> None:
    wire = format_sse(StreamEvent(event="token", data={"text": "çğş"}))
    assert "çğş" in wire  # ensure_ascii=False


async def test_sse_stream_serializes_all_events() -> None:
    async def gen():
        yield StreamEvent(event="token", data={"text": "a"})
        yield StreamEvent(event="citations", data={"citations": []})

    chunks = [c async for c in sse_stream(gen())]
    assert chunks[0].startswith("event: token")
    assert chunks[1].startswith("event: citations")


# --- Servis akışı (birim, ağsız) ---


async def test_stream_no_results_yields_canned_and_empty_citations(
    test_settings, fake_embedding, vector_store
) -> None:
    retrieval = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    service = ChatService(test_settings, retrieval, FakeLLM())
    events = await _collect(service.stream_answer("herhangi bir soru"))

    assert [e.event for e in events] == ["token", "citations"]
    assert events[0].data["text"] == NO_CONTEXT_ANSWER
    assert events[1].data["citations"] == []


async def test_stream_end_to_end_event_order_and_citation(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    from app.repositories.document_repo import DocumentRepository
    from app.services.ingestion import IngestionService

    repo = DocumentRepository(sessionmaker())
    ing = IngestionService(test_settings, fake_embedding, vector_store, repo, Bm25SparseEncoder())
    await ing.ingest(
        filename="qdrant.txt",
        data=b"Qdrant bir vektor veritabanidir. " * 30,
        category="db",
    )

    retrieval = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    service = ChatService(test_settings, retrieval, FakeLLM("Yanit [1] burada."))
    events = await _collect(service.stream_answer("vektor veritabani", top_k=3))

    kinds = [e.event for e in events]
    assert kinds[0] == "sources"  # kaynaklar baştan
    assert kinds[-1] == "citations"  # citation'lar sonda
    assert "token" in kinds

    # token'lar birleşince cevabı vermeli — [n] işaretleri kullanıcıya
    # gösterilen metinden temizlenir (citation'lar sonda ayrıca döner)
    answer = "".join(e.data["text"] for e in events if e.event == "token")
    assert answer.strip() == "Yanit burada."

    # baştaki kaynaklar 1-indexli marker taşımalı
    sources = events[0].data["sources"]
    assert sources[0]["marker"] == 1
    assert sources[0]["document_name"] == "qdrant.txt"

    # sondaki citation, cevaptaki [1] işaretinden türetilmeli
    citations = events[-1].data["citations"]
    assert len(citations) == 1
    assert citations[0]["marker"] == 1
    assert citations[0]["document_name"] == "qdrant.txt"


# --- API ucu (uçtan uca) ---


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Ham SSE gövdesini (event, data) çiftlerine ayrıştırır."""
    out: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        name = payload = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
        if name is not None:
            out.append((name, payload))
    return out


def test_chat_stream_after_upload(client: TestClient) -> None:
    data = ("LangChain LLM uygulamaları için bir çatıdır. " * 40).encode()
    up = client.post(
        "/api/v1/documents",
        files={"file": ("langchain.txt", data, "text/plain")},
        data={"category": "framework"},
    )
    assert up.status_code == 201

    resp = client.post(
        "/api/v1/chat/stream", json={"query": "LangChain nedir?", "top_k": 3}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    kinds = [name for name, _ in events]
    assert kinds[0] == "sources"
    assert "token" in kinds
    assert kinds[-1] == "citations"

    citations = events[-1][1]["citations"]
    assert citations
    assert citations[0]["document_name"] == "langchain.txt"


def test_chat_stream_no_documents_returns_canned(client: TestClient) -> None:
    resp = client.post("/api/v1/chat/stream", json={"query": "hiç doküman yok"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0][0] == "token"
    assert "bilgi bulamadım" in events[0][1]["text"].lower()


def test_chat_stream_empty_query_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/chat/stream", json={"query": ""})
    assert resp.status_code == 422
