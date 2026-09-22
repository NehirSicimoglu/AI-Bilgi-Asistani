"""Embedding sağlayıcı interface'i (port).

Doküman/sorgu metinlerini yoğun (dense) vektöre çevirir. Sağlayıcı değişse de
(Google, OpenAI, yerel sentence-transformers) servis kodu değişmez.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def dim(self) -> int:
        """Üretilen vektörün boyutu (Qdrant collection kurulumu için gerekir)."""
        ...

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Birden çok metni (indeksleme) topluca gömer."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Tek bir sorgu metnini gömer (retrieval)."""
        ...
