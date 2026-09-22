"""BM25 tarzı seyrek (sparse) kodlayıcı — hybrid retrieval için.

Metni token'lara böler, her token'ı büyük bir indeks uzayına hash'ler ("hashing
trick") ve BM25 terim-frekans doygunluğu uygulanmış ağırlığı değer olarak verir.
IDF sunucu tarafında Qdrant IDF modifier'ı ile uygulanır; böylece kodlayıcı
DURUMSUZDUR (korpus istatistiği gerektirmez) ve ingestion ile retrieval'da birebir
aynı çalışır — indeksleme/sorgu tutarlılığı garanti olur.

Karar: `fastembed` BM25 yerine saf-Python hashing BM25 seçildi. Gerekçe: (1) ağsız
→ test ve prod'da aynı davranış, sıfır model indirmesi; (2) durumsuz → avgdl gibi
korpus istatistiği taşımaz; (3) bağımlılık yükü yok. Kalite yetmezse `fastembed`
BM25/SPLADE aynı `SparseEncoder` arayüzünün arkasına takılabilir (interface
avantajı).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Protocol, runtime_checkable

from app.providers.vector_store.base import SparseVector

# u32 sınırının güvenli altında bir indeks uzayı; çakışma olasılığı düşük.
_VOCAB_SIZE = 2**31 - 1
# BM25 terim doygunluğu (k1). Uzunluk normalizasyonu (b) durumsuzluk için atlanır.
_K1 = 1.2
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Küçük, karma (TR + EN) stopword kümesi — çok yaygın terimlerin gürültüsünü azaltır.
# IDF zaten yaygın terimleri bastırır; bu yalnızca ek bir eleme.
_STOPWORDS = frozenset(
    {
        "ve", "veya", "ile", "bir", "bu", "şu", "o", "de", "da", "ki", "mi",
        "için", "gibi", "ama", "fakat", "ancak", "çok", "daha", "en", "the",
        "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
        "was", "were", "be", "with", "as", "by", "at", "this", "that",
    }
)


@runtime_checkable
class SparseEncoder(Protocol):
    """Metni BM25 tarzı seyrek vektöre çevirir (dense embedding'in sparse karşılığı)."""

    def encode(self, text: str) -> SparseVector:
        ...

    def encode_batch(self, texts: list[str]) -> list[SparseVector]:
        ...


class Bm25SparseEncoder:
    """Saf-Python, durumsuz, hashing tabanlı BM25 kodlayıcı."""

    def __init__(self, *, k1: float = _K1, vocab_size: int = _VOCAB_SIZE) -> None:
        self._k1 = k1
        self._vocab_size = vocab_size

    def _tokens(self, text: str) -> list[str]:
        return [
            t
            for t in (m.casefold() for m in _TOKEN_RE.findall(text))
            if t not in _STOPWORDS and len(t) > 1
        ]

    def _hash(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(digest, "big") % self._vocab_size

    def encode(self, text: str) -> SparseVector:
        # Aynı hash'e düşen token'ların terim frekansını topla (çakışmaları birleştir).
        tf: dict[int, float] = defaultdict(float)
        for token in self._tokens(text):
            tf[self._hash(token)] += 1.0
        if not tf:
            return SparseVector(indices=[], values=[])
        indices: list[int] = []
        values: list[float] = []
        for index, freq in tf.items():
            # BM25 doygunluğu: yüksek frekansın etkisini sınırlar.
            indices.append(index)
            values.append(freq * (self._k1 + 1.0) / (freq + self._k1))
        return SparseVector(indices=indices, values=values)

    def encode_batch(self, texts: list[str]) -> list[SparseVector]:
        return [self.encode(t) for t in texts]
