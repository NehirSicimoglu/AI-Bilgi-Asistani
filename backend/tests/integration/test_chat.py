"""RAG chat servisi + citation eşleme, ağsız."""

from __future__ import annotations

from app.ingestion.sparse import Bm25SparseEncoder
from app.models.domain import RetrievalResult
from app.services.chat import ChatService, _build_citations
from app.services.prompts import NO_CONTEXT_ANSWER
from app.services.retrieval import RetrievalService
from tests.conftest import FakeLLM


def _results() -> list[RetrievalResult]:
    return [
        RetrievalResult(
            chunk_id="c1",
            document_id="d1",
            document_name="k8s.txt",
            text="Kubernetes konteynerleri yönetir.",
            score=0.9,
            page=2,
        ),
        RetrievalResult(
            chunk_id="c2",
            document_id="d2",
            document_name="docker.txt",
            text="Docker imaj oluşturur.",
            score=0.7,
        ),
    ]


def test_build_citations_maps_markers() -> None:
    citations = _build_citations("Cevap [1] ve ayrıca [2].", _results())
    assert [c.marker for c in citations] == [1, 2]
    assert citations[0].document_name == "k8s.txt"
    assert citations[0].page == 2
    assert citations[0].chunk_id == "c1"


def test_build_citations_ignores_out_of_range() -> None:
    citations = _build_citations("Cevap [1] ve [9].", _results())
    assert [c.marker for c in citations] == [1]


def test_build_citations_dedup() -> None:
    citations = _build_citations("[1] tekrar [1].", _results())
    assert len(citations) == 1


async def test_chat_no_results_returns_canned(
    test_settings, fake_embedding, vector_store
) -> None:
    # boş bilgi tabanı → retrieval boş → LLM çağrılmaz
    retrieval = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    service = ChatService(test_settings, retrieval, FakeLLM())
    result = await service.answer("herhangi bir soru")
    assert result.answer == NO_CONTEXT_ANSWER
    assert result.citations == []


async def test_chat_end_to_end_with_citation(
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
    service = ChatService(test_settings, retrieval, FakeLLM("Yanit [1]."))
    result = await service.answer("vektor veritabani", top_k=3)

    assert "Yanit" in result.answer
    assert len(result.citations) == 1
    assert result.citations[0].document_name == "qdrant.txt"
    assert result.usage.total_tokens == 15
