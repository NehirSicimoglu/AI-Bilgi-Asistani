"""Gerçek altyapıya karşı entegrasyon testleri (testcontainers).

Diğer tüm testler kasıtlı olarak ağsızdır (SQLite + in-memory Qdrant); bu dosya
istisnadır: gerçek bir Postgres ve gerçek bir Qdrant sunucusu Docker container
olarak ayağa kaldırılıp kod bu gerçek sunuculara karşı çalıştırılır. Amaç,
SQLite/in-memory istemcinin gizlediği olabilecek farkları (örn. Postgres'in JSON
sütun/timezone davranışı, gerçek Qdrant sunucusunun Prefetch+filter semantiği)
yakalamaktır.

Docker daemon çalışmıyorsa modül tamamen atlanır (`pytest.skip`) — CI/geliştirme
ortamında Docker açık değilse suit kırılmaz, sadece bu testler pas geçilir.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.ingestion.sparse import Bm25SparseEncoder
from app.models.db import Base
from app.models.domain import Citation, Conversation, Message, Role
from app.providers.vector_store.base import VectorPoint
from app.providers.vector_store.qdrant import QdrantVectorStore
from app.repositories.conversation_repo import ConversationRepository

try:
    import docker
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs
    from testcontainers.postgres import PostgresContainer

    docker.from_env().ping()
    _DOCKER_AVAILABLE = True
except Exception:  # pragma: no cover - ortama bağlı
    _DOCKER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DOCKER_AVAILABLE, reason="Docker daemon çalışmıyor; gerçek altyapı testleri atlandı."
)


async def test_real_postgres_conversation_roundtrip() -> None:
    """SQLite'da geçen conversation repo testinin gerçek Postgres'e karşı doğrulaması."""
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        engine = create_async_engine(pg.get_connection_url())
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)

        repo = ConversationRepository(maker())
        conv = await repo.create(Conversation(title="Gerçek Postgres testi"))
        await repo.add_message(
            Message(conversation_id=conv.id, role=Role.USER, content="Merhaba")
        )
        await repo.add_message(
            Message(
                conversation_id=conv.id,
                role=Role.ASSISTANT,
                content="Selam [1].",
                citations=[
                    Citation(marker=1, chunk_id="c1", document_id="d1", document_name="a.md")
                ],
            )
        )

        messages = await repo.get_messages(conv.id)
        assert [m.content for m in messages] == ["Merhaba", "Selam [1]."]

        fetched = await repo.get(conv.id)
        assert fetched is not None
        assert fetched.updated_at >= fetched.created_at

        await engine.dispose()


async def test_real_qdrant_hybrid_search_with_filter() -> None:
    """Prefetch+filter düzeltmesini gerçek Qdrant sunucusuna karşı doğrular."""
    with DockerContainer("qdrant/qdrant:latest").with_exposed_ports(6333) as qdrant:
        wait_for_logs(qdrant, "Qdrant HTTP listening", timeout=30)
        host = qdrant.get_container_host_ip()
        port = qdrant.get_exposed_port(6333)

        from qdrant_client import AsyncQdrantClient

        settings = Settings(embedding_dim=4, qdrant_collection="real_kb")
        client = AsyncQdrantClient(url=f"http://{host}:{port}")
        store = QdrantVectorStore(settings, client=client)
        await store.ensure_collection()

        sparse_encoder = Bm25SparseEncoder()
        docs = [
            ("1", "Qdrant vektör aramasi icin kullanilir", "qdrant.md"),
            ("2", "Redis bir bellek ici veritabanidir", "redis.md"),
        ]
        points = [
            VectorPoint(
                id=pid,
                dense=[0.1, 0.2, 0.3, 0.4],
                sparse=sparse_encoder.encode(text),
                payload={
                    "chunk_id": pid,
                    "document_id": "doc",
                    "document_name": name,
                    "category": "databases",
                    "text": text,
                },
            )
            for pid, text, name in docs
        ]
        await store.upsert(points)

        results = await store.search(
            dense_vector=[0.1, 0.2, 0.3, 0.4],
            sparse_vector=sparse_encoder.encode("qdrant nedir"),
            top_k=5,
            mode="hybrid",
            filters={"category": "databases"},
        )
        assert any(r.payload.get("document_name") == "qdrant.md" for r in results)

        results_filtered_out = await store.search(
            dense_vector=[0.1, 0.2, 0.3, 0.4],
            sparse_vector=sparse_encoder.encode("qdrant nedir"),
            top_k=5,
            mode="hybrid",
            filters={"category": "yok"},
        )
        assert results_filtered_out == []
