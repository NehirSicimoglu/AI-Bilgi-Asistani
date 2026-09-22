"""Dense retrieval servisi, ağsız (fake embedding + in-memory Qdrant)."""

from __future__ import annotations

from app.ingestion.sparse import Bm25SparseEncoder
from app.repositories.document_repo import DocumentRepository
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService


async def _ingest_corpus(test_settings, fake_embedding, vector_store, sessionmaker) -> None:
    repo = DocumentRepository(sessionmaker())
    ing = IngestionService(test_settings, fake_embedding, vector_store, repo, Bm25SparseEncoder())
    await ing.ingest(
        filename="k8s.txt",
        data=b"Kubernetes konteyner orkestrasyon platformudur. " * 30,
        category="docs",
    )
    await ing.ingest(
        filename="fastapi.txt",
        data=b"FastAPI Python icin modern web cercevesidir. " * 30,
        category="framework",
    )


async def test_retrieve_returns_results(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _ingest_corpus(test_settings, fake_embedding, vector_store, sessionmaker)
    service = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())

    results = await service.retrieve("konteyner", top_k=3)
    assert results
    assert all(r.text for r in results)
    assert all(r.document_id for r in results)
    # skorlar azalan sırada olmalı
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


async def test_retrieve_respects_top_k(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _ingest_corpus(test_settings, fake_embedding, vector_store, sessionmaker)
    service = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    results = await service.retrieve("herhangi bir sorgu", top_k=2)
    assert len(results) <= 2


async def test_retrieve_with_filter(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _ingest_corpus(test_settings, fake_embedding, vector_store, sessionmaker)
    service = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    results = await service.retrieve(
        "sorgu", top_k=10, filters={"category": "framework"}
    )
    assert results
    assert all(r.document_name == "fastapi.txt" for r in results)
