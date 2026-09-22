"""Vektör veritabanı interface'i (port).

Dense + sparse (BM25) + hybrid aramayı ve metadata filtrelemeyi kapsayacak
şekilde tasarlandı; böylece interface değişmeden hybrid ve filtre
eklenebilir. Somut sağlayıcı Qdrant'tır; ileride başka bir vektör DB'ye geçmek
yalnızca bu Protocol'ü implemente etmeyi gerektirir.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

SearchMode = Literal["dense", "hybrid"]


class SparseVector(BaseModel):
    """BM25/SPLADE tipi seyrek vektör (indeks → ağırlık)."""

    indices: list[int]
    values: list[float]


class VectorPoint(BaseModel):
    """Qdrant'a yazılacak bir nokta: dense + (opsiyonel) sparse + payload."""

    id: str
    dense: list[float]
    sparse: SparseVector | None = None
    payload: dict = Field(default_factory=dict)


class ScoredPoint(BaseModel):
    """Aramadan dönen skorlu nokta."""

    id: str
    score: float
    payload: dict = Field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    async def ensure_collection(self) -> None:
        """Collection yoksa dense + named sparse vector ile oluşturur (idempotent)."""
        ...

    async def reset_collection(self) -> None:
        """Collection'ı siler ve boş olarak yeniden kurar (sıfırdan indeksleme)."""
        ...

    async def upsert(self, points: list[VectorPoint]) -> None:
        """Noktaları ekler/günceller."""
        ...

    async def search(
        self,
        *,
        dense_vector: list[float],
        top_k: int,
        mode: SearchMode = "dense",
        sparse_vector: SparseVector | None = None,
        filters: dict | None = None,
    ) -> list[ScoredPoint]:
        """dense veya hybrid (dense+sparse, RRF) arama; opsiyonel metadata filtresi."""
        ...

    async def delete_by_document(self, document_id: str) -> None:
        """Bir dokümana ait tüm noktaları siler."""
        ...

    async def count(self) -> int:
        """Toplam nokta (chunk) sayısı — admin dashboard için."""
        ...

    async def scroll(
        self,
        *,
        limit: int = 50,
        offset: str | None = None,
        document_id: str | None = None,
    ) -> tuple[list[ScoredPoint], str | None]:
        """Skorsuz sayfalı chunk listesi (Admin Dashboard'da inceleme için).

        `offset=None` ilk sayfa; dönen `next_offset` bir sonraki çağrıya verilir,
        `None` ise son sayfadır. `document_id` verilirse yalnızca o dokümanın
        chunk'ları döner (doküman-bazlı inceleme için).
        """
        ...
