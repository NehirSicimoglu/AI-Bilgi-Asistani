"""Qdrant vektör deposu (async in-memory, ağ gerektirmez)."""

from __future__ import annotations

import pytest
from qdrant_client import AsyncQdrantClient

from app.config import Settings
from app.providers.vector_store.base import SparseVector, VectorPoint, VectorStore
from app.providers.vector_store.qdrant import QdrantVectorStore


@pytest.fixture
async def store() -> QdrantVectorStore:
    settings = Settings(embedding_dim=4, qdrant_collection="test_kb")
    s = QdrantVectorStore(settings, client=AsyncQdrantClient(location=":memory:"))
    await s.ensure_collection()
    return s


def _pt(id_: str, dense: list[float], doc: str, text: str, **extra) -> VectorPoint:
    return VectorPoint(
        id=id_,
        dense=dense,
        payload={"document_id": doc, "text": text, "chunk_id": id_, **extra},
    )


async def test_interface(store: QdrantVectorStore) -> None:
    assert isinstance(store, VectorStore)


async def test_ensure_collection_idempotent(store: QdrantVectorStore) -> None:
    await store.ensure_collection()  # ikinci çağrı hata vermemeli
    assert await store.count() == 0


async def test_upsert_and_dense_search(store: QdrantVectorStore) -> None:
    await store.upsert(
        [
            _pt("a", [1.0, 0.0, 0.0, 0.0], "d1", "elma"),
            _pt("b", [0.0, 1.0, 0.0, 0.0], "d2", "armut"),
        ]
    )
    assert await store.count() == 2
    hits = await store.search(dense_vector=[1.0, 0.0, 0.0, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0].payload["text"] == "elma"
    assert hits[0].score > 0


async def test_metadata_filter(store: QdrantVectorStore) -> None:
    await store.upsert(
        [
            _pt("a", [1.0, 0.0, 0.0, 0.0], "d1", "elma", category="fruit"),
            _pt("b", [0.9, 0.1, 0.0, 0.0], "d2", "kalem", category="office"),
        ]
    )
    hits = await store.search(
        dense_vector=[1.0, 0.0, 0.0, 0.0], top_k=5, filters={"category": "office"}
    )
    assert len(hits) == 1
    assert hits[0].payload["category"] == "office"


async def test_delete_by_document(store: QdrantVectorStore) -> None:
    await store.upsert(
        [
            _pt("a", [1.0, 0.0, 0.0, 0.0], "d1", "x"),
            _pt("b", [0.0, 1.0, 0.0, 0.0], "d1", "y"),
            _pt("c", [0.0, 0.0, 1.0, 0.0], "d2", "z"),
        ]
    )
    await store.delete_by_document("d1")
    assert await store.count() == 1


async def test_hybrid_search_with_sparse(store: QdrantVectorStore) -> None:
    await store.upsert(
        [
            VectorPoint(
                id="a",
                dense=[1.0, 0.0, 0.0, 0.0],
                sparse=SparseVector(indices=[1, 5], values=[0.9, 0.4]),
                payload={"document_id": "d1", "text": "hibrit", "chunk_id": "a"},
            )
        ]
    )
    hits = await store.search(
        dense_vector=[1.0, 0.0, 0.0, 0.0],
        top_k=3,
        mode="hybrid",
        sparse_vector=SparseVector(indices=[1, 5], values=[0.5, 0.5]),
    )
    assert len(hits) == 1
    assert hits[0].payload["text"] == "hibrit"
