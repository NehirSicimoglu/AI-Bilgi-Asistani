"""Google embedding sağlayıcısı (fake istemci ile, ağ gerektirmez)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.exceptions import ProviderError
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.google import GoogleEmbeddingProvider


class _FakeAioModels:
    def __init__(self, dim: int, fail: bool = False) -> None:
        self._dim = dim
        self._fail = fail
        self.calls: list[dict] = []

    async def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._fail:
            raise RuntimeError("boom")
        embeddings = [SimpleNamespace(values=[0.1] * self._dim) for _ in contents]
        return SimpleNamespace(embeddings=embeddings)


class _FakeClient:
    def __init__(self, dim: int, fail: bool = False) -> None:
        self.aio = SimpleNamespace(models=_FakeAioModels(dim, fail))


def _settings() -> Settings:
    return Settings(embedding_model="text-embedding-004", embedding_dim=8)


def test_provider_satisfies_interface() -> None:
    provider = GoogleEmbeddingProvider(_settings(), client=_FakeClient(8))
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dim == 8


async def test_embed_texts_batches_and_shapes() -> None:
    client = _FakeClient(8)
    provider = GoogleEmbeddingProvider(_settings(), client=client)
    vectors = await provider.embed_texts(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 8 for v in vectors)
    # doküman task_type kullanılmalı
    assert client.aio.models.calls[0]["config"].task_type == "RETRIEVAL_DOCUMENT"


async def test_embed_query_uses_query_task_type() -> None:
    client = _FakeClient(8)
    provider = GoogleEmbeddingProvider(_settings(), client=client)
    vec = await provider.embed_query("soru")
    assert len(vec) == 8
    assert client.aio.models.calls[0]["config"].task_type == "RETRIEVAL_QUERY"


async def test_embed_empty_returns_empty() -> None:
    provider = GoogleEmbeddingProvider(_settings(), client=_FakeClient(8))
    assert await provider.embed_texts([]) == []


async def test_provider_error_wrapped() -> None:
    provider = GoogleEmbeddingProvider(_settings(), client=_FakeClient(8, fail=True))
    with pytest.raises(ProviderError):
        await provider.embed_query("x")


def test_missing_api_key_raises() -> None:
    settings = Settings(gemini_api_key=None)
    with pytest.raises(RuntimeError):
        GoogleEmbeddingProvider(settings)  # client=None → api_key gerekli
