"""Metadata filtreleme (tür/tarih aralığı), ağsız. Hafif kapsam.

Kapsamlı filtre kombinasyonları kapsam dışı bırakıldı; burada yeni kablolama
(payload extension/created_at + Range builder + MetadataFilter) doğrulanır.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api.schemas.filters import MetadataFilter
from app.ingestion.sparse import Bm25SparseEncoder
from app.repositories.document_repo import DocumentRepository
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService


async def _service(test_settings, fake_embedding, vector_store, sessionmaker):
    repo = DocumentRepository(sessionmaker())
    ing = IngestionService(
        test_settings, fake_embedding, vector_store, repo, Bm25SparseEncoder()
    )
    await ing.ingest(filename="a.txt", data=b"metin dosyasi icerigi. " * 20, category="x")
    await ing.ingest(filename="b.md", data=b"# Markdown\n\nbaslik icerigi. " * 20, category="y")
    return RetrievalService(
        test_settings, fake_embedding, vector_store, Bm25SparseEncoder()
    )


async def test_extension_filter(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    service = await _service(test_settings, fake_embedding, vector_store, sessionmaker)
    flt = MetadataFilter(extension=".md").to_filters()
    results = await service.retrieve("icerik", top_k=10, filters=flt)
    assert results
    assert all(r.document_name == "b.md" for r in results)


async def test_created_at_range_filter(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    service = await _service(test_settings, fake_embedding, vector_store, sessionmaker)
    future = datetime.now(UTC) + timedelta(days=1)
    past = datetime.now(UTC) - timedelta(days=1)

    # Gelecekten sonra oluşturulmuş yok → boş.
    assert await service.retrieve(
        "icerik", top_k=10, filters=MetadataFilter(created_after=future).to_filters()
    ) == []
    # Dünden sonra oluşturulmuş hepsi → dolu.
    assert await service.retrieve(
        "icerik", top_k=10, filters=MetadataFilter(created_after=past).to_filters()
    )


def test_metadata_filter_to_filters_shapes() -> None:
    assert MetadataFilter().to_filters() is None
    spec = MetadataFilter(category=["a", "b"], extension=".pdf").to_filters()
    assert spec == {"category": ["a", "b"], "extension": ".pdf"}
    when = datetime(2026, 1, 1, tzinfo=UTC)
    ranged = MetadataFilter(created_after=when).to_filters()
    assert ranged == {"created_at": {"gte": when.timestamp()}}
