"""Hybrid retrieval (BM25 sparse + dense, RRF), ağsız.

Fake embedding anlamsal olarak rastgeledir; bu yüzden nadir bir anahtar kelimeyle
yapılan sorguda DENSE tek başına doğru dokümanı güvenilir getirmez. HYBRID, BM25
sparse bileşeni sayesinde tam kelime eşleşmesini üste taşır — testin kanıtladığı da
budur (sparse'ın kattığı değer).
"""

from __future__ import annotations

from app.ingestion.sparse import Bm25SparseEncoder
from app.repositories.document_repo import DocumentRepository
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService

# Yalnızca tek dokümanda geçen nadir, ayırt edici terim.
_RARE = "Zephyrium"


async def _ingest(test_settings, fake_embedding, vector_store, sessionmaker) -> None:
    repo = DocumentRepository(sessionmaker())
    ing = IngestionService(
        test_settings, fake_embedding, vector_store, repo, Bm25SparseEncoder()
    )
    await ing.ingest(
        filename="rare.txt",
        data=(f"{_RARE} nadir bir elementtir ve özel alaşımlarda kullanılır. " * 20).encode(),
        category="chem",
    )
    await ing.ingest(
        filename="generic.txt",
        data=(b"Genel amacli sistemler farkli senaryolarda kullanilir. " * 20),
        category="misc",
    )


async def test_hybrid_surfaces_exact_keyword_match(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _ingest(test_settings, fake_embedding, vector_store, sessionmaker)
    service = RetrievalService(
        test_settings, fake_embedding, vector_store, Bm25SparseEncoder()
    )

    results = await service.retrieve(_RARE, top_k=5, mode="hybrid")

    assert results
    # BM25 sparse bileşeni nadir terimi içeren dokümanı en üste taşır.
    assert results[0].document_name == "rare.txt"
    assert _RARE.casefold() in results[0].text.casefold()


async def test_hybrid_and_dense_both_run(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _ingest(test_settings, fake_embedding, vector_store, sessionmaker)
    service = RetrievalService(
        test_settings, fake_embedding, vector_store, Bm25SparseEncoder()
    )

    dense = await service.retrieve("element", top_k=3, mode="dense")
    hybrid = await service.retrieve("element", top_k=3, mode="hybrid")

    # Her iki mod da çalışır ve skorları azalan sırada döner.
    for res in (dense, hybrid):
        assert res
        scores = [r.score for r in res]
        assert scores == sorted(scores, reverse=True)


async def test_hybrid_respects_metadata_filter(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _ingest(test_settings, fake_embedding, vector_store, sessionmaker)
    service = RetrievalService(
        test_settings, fake_embedding, vector_store, Bm25SparseEncoder()
    )

    # Filtre hybrid modda da (her prefetch alt-sorgusuna) uygulanır.
    results = await service.retrieve(
        _RARE, top_k=10, mode="hybrid", filters={"category": "misc"}
    )
    assert all(r.document_name == "generic.txt" for r in results)
