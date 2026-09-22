"""MCP Server (ağsız): search_documents ve ask_question tool'ları."""

from __future__ import annotations

import json

from app.ingestion.sparse import Bm25SparseEncoder
from app.mcp.server import create_server
from app.repositories.document_repo import DocumentRepository
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService
from tests.conftest import FakeLLM


async def _server(test_settings, fake_embedding, vector_store, sessionmaker):
    async with sessionmaker() as session:
        ing = IngestionService(
            test_settings,
            fake_embedding,
            vector_store,
            DocumentRepository(session),
            Bm25SparseEncoder(),
        )
        await ing.ingest(
            filename="qdrant-overview.md",
            data=b"Qdrant bir vektor veritabanidir ve benzerlik aramasi yapar. " * 15,
            category="databases",
        )

    retrieval = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    llm = FakeLLM("Qdrant bir vektor veritabanidir [1].")
    return create_server(test_settings, retrieval, llm, sessionmaker)


def _payload(result) -> dict | list:
    """FastMCP call_tool iki farklı şekilde dönebilir:

    - `list` dönen tool'lar için `(content_blocks, {"result": [...]})` tuple'ı
      (yapılandırılmış çıktı şeması listenin adlandırılmamış öğesini sarmalar).
    - `dict` dönen tool'lar için (serbest biçimli şema) düz `list[ContentBlock]`;
      ilk metin bloğu JSON olarak parse edilir.
    """
    if isinstance(result, tuple):
        _content, structured = result
        if set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    return json.loads(result[0].text)


async def test_search_documents_tool_returns_hits(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    server = await _server(test_settings, fake_embedding, vector_store, sessionmaker)
    names = {t.name for t in await server.list_tools()}
    assert {"search_documents", "ask_question"} <= names

    raw = await server.call_tool("search_documents", {"query": "Qdrant nedir?", "top_k": 3})
    hits = _payload(raw)
    assert isinstance(hits, list) and len(hits) >= 1
    assert hits[0]["document_name"] == "qdrant-overview.md"


async def test_search_documents_tool_respects_category_filter(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    server = await _server(test_settings, fake_embedding, vector_store, sessionmaker)

    raw = await server.call_tool(
        "search_documents", {"query": "Qdrant nedir?", "category": "yok-boyle-kategori"}
    )
    assert _payload(raw) == []


async def test_ask_question_tool_returns_answer_with_citations(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    server = await _server(test_settings, fake_embedding, vector_store, sessionmaker)

    raw = await server.call_tool("ask_question", {"question": "Qdrant nedir?"})
    payload = _payload(raw)
    assert "Qdrant" in payload["answer"]
    assert len(payload["citations"]) >= 1
    assert payload["citations"][0]["document_name"] == "qdrant-overview.md"
