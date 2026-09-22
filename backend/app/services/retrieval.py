"""Retrieval servisi — sorguyu ilgili chunk'lara çevirir.

İki mod: `dense` (yalnız yoğun vektör) ve `hybrid` (dense + BM25 sparse, sunucu
tarafı RRF fusion). Hybrid modda sorgu, dense embedding'in yanında BM25 sparse
vektöre de kodlanır; iki aday listesi Qdrant Query API `prefetch` + RRF ile
birleştirilir. Sparse vektör indeksleme sırasında (ingestion) üretildiğinden
yeniden indeksleme gerekmez.
"""

from __future__ import annotations

import asyncio
import time

from app.config import Settings
from app.ingestion.sparse import SparseEncoder
from app.logging import get_logger
from app.models.domain import RetrievalResult
from app.observability import observe_retrieval
from app.providers.embedding.base import EmbeddingProvider
from app.providers.vector_store.base import ScoredPoint, SearchMode, VectorStore

logger = get_logger(__name__)

# Payload'da RetrievalResult'ın kendi alanlarına giden anahtarlar (metadata'dan hariç tutulur)
_RESERVED_KEYS = {"chunk_id", "document_id", "document_name", "text", "page"}


def _round_robin_dedup(
    lists: list[list[RetrievalResult]],
) -> list[RetrievalResult]:
    """Alt-sorgu sonuç listelerini sıra-sıra birleştirip chunk_id'ye göre tekilleştirir.

    Sıra: tüm listelerin 0. elemanı, sonra 1.'leri... Bir chunk birden çok alt-sorguda
    çıkarsa yalnızca İLK görüldüğü yerde tutulur (en yüksek yerel sırasıyla). Böylece
    hiçbir alt-sorgu diğerini bastırmaz; kapsama korunur.
    """
    seen: set[str] = set()
    merged: list[RetrievalResult] = []
    depth = max((len(lst) for lst in lists), default=0)
    for rank in range(depth):
        for lst in lists:
            if rank < len(lst):
                r = lst[rank]
                if r.chunk_id not in seen:
                    seen.add(r.chunk_id)
                    merged.append(r)
    return merged


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        embedding: EmbeddingProvider,
        vector_store: VectorStore,
        sparse_encoder: SparseEncoder,
    ) -> None:
        self._settings = settings
        self._embedding = embedding
        self._vector_store = vector_store
        self._sparse = sparse_encoder

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        mode: SearchMode | None = None,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        top_k = top_k or self._settings.retrieval_top_k
        mode = mode or self._settings.retrieval_mode

        start = time.perf_counter()
        query_vector = await self._embedding.embed_query(query)
        # Hybrid modda sorgunun BM25 sparse karşılığını da üret; RRF fusion Qdrant'ta.
        sparse_vector = self._sparse.encode(query) if mode == "hybrid" else None
        hits = await self._vector_store.search(
            dense_vector=query_vector,
            top_k=top_k,
            mode=mode,
            sparse_vector=sparse_vector,
            filters=filters,
        )
        results = [self._to_result(h) for h in hits]
        elapsed = time.perf_counter() - start
        observe_retrieval(mode, elapsed)
        logger.info(
            "retrieval_done",
            query_len=len(query),
            mode=mode,
            hits=len(results),
            duration_ms=round(elapsed * 1000, 2),
        )
        return results

    async def retrieve_multi(
        self,
        subqueries: list[str],
        *,
        top_k: int | None = None,
        mode: SearchMode | None = None,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        """Çok alt-sorgulu (multi-query) getirme — Query Decomposition için.

        Her alt-sorgu ayrı ayrı (paralel) getirilir; sonuçlar ``chunk_id``'ye göre
        tekilleştirilip round-robin (sıra-sıra) birleştirilir: önce her alt-sorgunun
        1. sonucu, sonra 2.'leri... Böylece baskın konu tüm bağlamı doldurmaz, her
        alt-sorgunun en iyi chunk'ları temsil edilir (çapraz-belge kapsaması).

        ``top_k`` burada ALT-SORGU BAŞINA sonuç sayısıdır (``subquery_top_k``).
        Tek alt-sorgu verilirse normal ``retrieve``'e düşer.
        """
        per_query_k = top_k or self._settings.subquery_top_k
        mode = mode or self._settings.retrieval_mode
        if len(subqueries) <= 1:
            q = subqueries[0] if subqueries else ""
            return await self.retrieve(q, top_k=per_query_k, mode=mode, filters=filters)

        start = time.perf_counter()
        lists = await asyncio.gather(
            *(
                self.retrieve(q, top_k=per_query_k, mode=mode, filters=filters)
                for q in subqueries
            )
        )
        merged = _round_robin_dedup(lists)
        elapsed = time.perf_counter() - start
        observe_retrieval(mode, elapsed)
        logger.info(
            "retrieval_multi_done",
            subqueries=len(subqueries),
            per_query_k=per_query_k,
            merged_hits=len(merged),
            duration_ms=round(elapsed * 1000, 2),
        )
        return merged

    @staticmethod
    def _to_result(point: ScoredPoint) -> RetrievalResult:
        payload = point.payload or {}
        return RetrievalResult(
            chunk_id=payload.get("chunk_id", point.id),
            document_id=payload.get("document_id", ""),
            document_name=payload.get("document_name", ""),
            text=payload.get("text", ""),
            score=point.score,
            page=payload.get("page"),
            metadata={k: v for k, v in payload.items() if k not in _RESERVED_KEYS},
        )
