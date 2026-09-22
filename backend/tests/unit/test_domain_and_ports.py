"""Domain modelleri ve sağlayıcı Protocol'leri.

Protocol'ler `runtime_checkable`; bir fake sağlayıcının yapısal olarak
interface'e uyduğunu isinstance ile doğrularız (structural typing).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.models.domain import Chunk, Citation, Document, DocumentStatus, Role
from app.providers.embedding.base import EmbeddingProvider
from app.providers.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.providers.vector_store.base import ScoredPoint, VectorPoint, VectorStore


def test_document_defaults() -> None:
    doc = Document(filename="x.pdf", extension=".pdf")
    assert doc.status is DocumentStatus.PENDING
    assert len(doc.id) == 32  # uuid4 hex
    assert doc.num_chunks == 0


def test_chunk_and_citation() -> None:
    chunk = Chunk(document_id="d1", index=0, text="merhaba", page=1)
    assert chunk.page == 1
    cit = Citation(marker=1, chunk_id=chunk.id, document_id="d1", document_name="x.pdf")
    assert cit.marker == 1


class _FakeLLM:
    async def generate(
        self, messages, *, system=None, temperature=None, max_tokens=None, model=None
    ):
        return LLMResponse(text="ok")

    async def stream(
        self, messages, *, system=None, temperature=None, max_tokens=None
    ) -> AsyncIterator[str]:
        yield "o"
        yield "k"


class _FakeEmbedding:
    @property
    def dim(self) -> int:
        return 3

    async def embed_texts(self, texts):
        return [[0.0, 0.0, 0.0] for _ in texts]

    async def embed_query(self, text):
        return [0.0, 0.0, 0.0]


class _FakeStore:
    async def ensure_collection(self) -> None: ...
    async def reset_collection(self) -> None: ...
    async def upsert(self, points) -> None: ...
    async def search(self, *, dense_vector, top_k, mode="dense", sparse_vector=None, filters=None):
        return [ScoredPoint(id="1", score=1.0)]
    async def delete_by_document(self, document_id) -> None: ...
    async def count(self) -> int:
        return 0
    async def scroll(self, *, limit=50, offset=None):
        return ([], None)


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(_FakeLLM(), LLMProvider)
    assert isinstance(_FakeEmbedding(), EmbeddingProvider)
    assert isinstance(_FakeStore(), VectorStore)


async def test_fake_llm_stream() -> None:
    llm = _FakeLLM()
    out = "".join([c async for c in llm.stream([LLMMessage(role=Role.USER, content="hi")])])
    assert out == "ok"


def test_vector_point_shape() -> None:
    p = VectorPoint(id="1", dense=[0.1, 0.2], payload={"document_id": "d1"})
    assert p.sparse is None
    assert p.payload["document_id"] == "d1"
