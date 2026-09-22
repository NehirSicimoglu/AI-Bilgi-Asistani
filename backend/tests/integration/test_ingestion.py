"""Ingestion servisi (servis + API), ağsız."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.exceptions import CorruptFileError, UnsupportedFileTypeError
from app.ingestion.sparse import Bm25SparseEncoder
from app.models.domain import DocumentStatus
from app.repositories.document_repo import DocumentRepository
from app.services.ingestion import IngestionService
from tests.conftest import FakeEmbedding


async def _service(
    settings: Settings,
    embedding: FakeEmbedding,
    vector_store,
    maker: async_sessionmaker,
) -> tuple[IngestionService, DocumentRepository]:
    session = maker()
    repo = DocumentRepository(session)
    return IngestionService(settings, embedding, vector_store, repo, Bm25SparseEncoder()), repo


async def test_ingest_txt_end_to_end(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    service, repo = await _service(
        test_settings, fake_embedding, vector_store, sessionmaker
    )
    content = ("Kubernetes bir konteyner orkestrasyon sistemidir. " * 40).encode()
    doc = await service.ingest(filename="k8s.txt", data=content, category="docs")

    assert doc.status is DocumentStatus.INDEXED
    assert doc.num_chunks > 0
    assert await vector_store.count() == doc.num_chunks

    stored = await repo.get(doc.id)
    assert stored is not None
    assert stored.category == "docs"

    # Chunk'lar Qdrant'ta aranabilir olmalı
    qvec = await fake_embedding.embed_query("konteyner")
    hits = await vector_store.search(dense_vector=qvec, top_k=3)
    assert hits
    assert hits[0].payload["document_id"] == doc.id


async def test_unsupported_type_rejected(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    """Desteklenmeyen uzantı doğrulamada elenir — doküman kaydı hiç oluşmaz."""
    service, repo = await _service(
        test_settings, fake_embedding, vector_store, sessionmaker
    )
    with pytest.raises(UnsupportedFileTypeError):
        await service.ingest(filename="kurulum.exe", data=b"x", category=None)

    assert await repo.count() == 0


async def test_corrupt_file_marks_failed(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    """Uzantı desteklense de içerik bozuksa kayıt FAILED işaretlenip hata verilir."""
    service, repo = await _service(
        test_settings, fake_embedding, vector_store, sessionmaker
    )
    with pytest.raises(CorruptFileError):
        await service.ingest(
            filename="bozuk.xlsx", data=b"gecerli bir xlsx degil", category=None
        )

    docs = await repo.list()
    assert len(docs) == 1
    assert docs[0].status is DocumentStatus.FAILED
    assert docs[0].error


async def test_delete_removes_vectors(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    service, repo = await _service(
        test_settings, fake_embedding, vector_store, sessionmaker
    )
    doc = await service.ingest(filename="a.txt", data=b"bir metin " * 50, category=None)
    assert await vector_store.count() > 0

    ok = await service.delete(doc.id)
    assert ok
    assert await vector_store.count() == 0
    assert await repo.get(doc.id) is None
