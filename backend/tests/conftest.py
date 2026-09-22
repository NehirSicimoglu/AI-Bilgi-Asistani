"""Ortak test fixture'ları — ağsız (SQLite + in-memory Qdrant + fake embedding)."""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.db import Base
from app.providers.vector_store.qdrant import QdrantVectorStore

EMBED_DIM = 8


class FakeEmbedding:
    """Deterministik, ağsız embedding — metinden sabit bir vektör üretir."""

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        raw = [digest[i % len(digest)] / 255.0 for i in range(self._dim)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FakeLLM:
    """Deterministik, ağsız LLM — verilen bağlamdaki ilk kaynağa [1] ile atıf yapar."""

    def __init__(self, answer: str = "İşte cevap [1].") -> None:
        self._answer = answer

    async def generate(
        self, messages, *, system=None, temperature=None, max_tokens=None, model=None
    ):
        from app.models.domain import TokenUsage
        from app.providers.llm.base import LLMResponse

        return LLMResponse(
            text=self._answer,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def stream(self, messages, *, system=None, temperature=None, max_tokens=None):
        for piece in self._answer.split(" "):
            yield piece + " "


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        embedding_dim=EMBED_DIM,
        qdrant_collection="test_kb",
        chunk_size=60,
        chunk_overlap=10,
    )


@pytest.fixture
def fake_embedding() -> FakeEmbedding:
    return FakeEmbedding()


@pytest.fixture
async def vector_store(test_settings: Settings) -> QdrantVectorStore:
    store = QdrantVectorStore(
        test_settings, client=AsyncQdrantClient(location=":memory:")
    )
    await store.ensure_collection()
    return store


@pytest.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.fixture
async def client(monkeypatch) -> AsyncIterator[TestClient]:
    """Tam uygulama + DI override (ağsız).

    SQLite (StaticPool) + in-memory Qdrant + fake embedding.
    """
    from app.config import get_settings
    from app.database import get_session
    from app.dependencies import (
        get_embedding_provider,
        get_llm_provider,
        get_vector_store,
    )
    from app.main import create_app

    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    settings = Settings(
        environment="test", embedding_dim=EMBED_DIM, qdrant_collection="api_kb"
    )

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    store = QdrantVectorStore(settings, client=AsyncQdrantClient(location=":memory:"))
    await store.ensure_collection()

    async def _override_session():
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbedding()
    app.dependency_overrides[get_vector_store] = lambda: store
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()

    with TestClient(app) as c:
        yield c

    await engine.dispose()
    get_settings.cache_clear()
