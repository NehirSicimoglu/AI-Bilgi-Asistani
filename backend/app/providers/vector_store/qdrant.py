"""Qdrant vektör deposu — `VectorStore` implementasyonu.

Collection **named dense + named sparse** vektörle kurulur. Sparse vektör
verildiğinde Qdrant Query API'si ile server-side RRF fusion yapılır (varsayılan
`retrieval_mode=hybrid`); verilmediğinde salt dense aramaya düşer. Fusion'ın
sunucu tarafında olması, adayları istemciye çekip birleştirme maliyetini önler.

Test için `AsyncQdrantClient(location=":memory:")` enjekte edilebilir.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.exceptions import ProviderError
from app.logging import get_logger
from app.providers.vector_store.base import ScoredPoint, SearchMode, SparseVector, VectorPoint

logger = get_logger(__name__)

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"


def _to_point_id(raw: str) -> str:
    """Chunk id'sini geçerli bir Qdrant UUID point id'sine çevirir (deterministik)."""
    try:
        return str(UUID(hex=raw))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, raw))


class QdrantVectorStore:
    def __init__(self, settings: Settings, client: AsyncQdrantClient | None = None) -> None:
        self._collection = settings.qdrant_collection
        self._dim = settings.embedding_dim
        self._client = client or AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )

    async def ensure_collection(self) -> None:
        try:
            if await self._client.collection_exists(self._collection):
                return
            await self._client.create_collection(
                self._collection,
                vectors_config={
                    DENSE_VECTOR: models.VectorParams(
                        size=self._dim, distance=models.Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR: models.SparseVectorParams(
                        modifier=models.Modifier.IDF
                    )
                },
            )
            logger.info("qdrant_collection_created", collection=self._collection, dim=self._dim)
        except Exception as exc:
            raise ProviderError(f"Qdrant collection hazırlanamadı: {exc}") from exc

    async def reset_collection(self) -> None:
        try:
            await self._client.delete_collection(self._collection)
        except Exception as exc:
            # Collection zaten yoksa silme başarısız olabilir; sonuç aynı.
            logger.warning("qdrant_collection_delete_skipped", error=str(exc))
        await self.ensure_collection()

    async def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        structs: list[models.PointStruct] = []
        for p in points:
            vector: dict = {DENSE_VECTOR: p.dense}
            if p.sparse is not None:
                vector[SPARSE_VECTOR] = models.SparseVector(
                    indices=p.sparse.indices, values=p.sparse.values
                )
            structs.append(
                models.PointStruct(id=_to_point_id(p.id), vector=vector, payload=p.payload)
            )
        try:
            await self._client.upsert(self._collection, points=structs)
        except Exception as exc:
            raise ProviderError(f"Qdrant upsert başarısız: {exc}") from exc

    async def search(
        self,
        *,
        dense_vector: list[float],
        top_k: int,
        mode: SearchMode = "dense",
        sparse_vector: SparseVector | None = None,
        filters: dict | None = None,
    ) -> list[ScoredPoint]:
        query_filter = _build_filter(filters)
        try:
            if mode == "hybrid" and sparse_vector is not None:
                # Filtre HER prefetch alt-sorgusuna verilmeli; üst seviye fusion
                # query'sine verilen filtre alt-sorgulara yayılmaz (aksi halde
                # metadata filtresi hybrid modda etkisiz kalır).
                result = await self._client.query_points(
                    self._collection,
                    prefetch=[
                        models.Prefetch(
                            query=dense_vector,
                            using=DENSE_VECTOR,
                            limit=top_k * 4,
                            filter=query_filter,
                        ),
                        models.Prefetch(
                            query=models.SparseVector(
                                indices=sparse_vector.indices, values=sparse_vector.values
                            ),
                            using=SPARSE_VECTOR,
                            limit=top_k * 4,
                            filter=query_filter,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    limit=top_k,
                    with_payload=True,
                )
            else:
                result = await self._client.query_points(
                    self._collection,
                    query=dense_vector,
                    using=DENSE_VECTOR,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
        except Exception as exc:
            raise ProviderError(f"Qdrant arama başarısız: {exc}") from exc

        return [
            ScoredPoint(id=str(p.id), score=p.score, payload=p.payload or {})
            for p in result.points
        ]

    async def delete_by_document(self, document_id: str) -> None:
        try:
            await self._client.delete(
                self._collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
            )
        except Exception as exc:
            raise ProviderError(f"Qdrant silme başarısız: {exc}") from exc

    async def count(self) -> int:
        try:
            return (await self._client.count(self._collection)).count
        except Exception as exc:
            raise ProviderError(f"Qdrant count başarısız: {exc}") from exc

    async def scroll(
        self,
        *,
        limit: int = 50,
        offset: str | None = None,
        document_id: str | None = None,
    ) -> tuple[list[ScoredPoint], str | None]:
        scroll_filter = (
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            )
            if document_id
            else None
        )
        try:
            points, next_offset = await self._client.scroll(
                self._collection,
                limit=limit,
                offset=offset,
                scroll_filter=scroll_filter,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise ProviderError(f"Qdrant scroll başarısız: {exc}") from exc
        return (
            [ScoredPoint(id=str(p.id), score=0.0, payload=p.payload or {}) for p in points],
            str(next_offset) if next_offset is not None else None,
        )


_RANGE_KEYS = frozenset({"gt", "gte", "lt", "lte"})


def _build_filter(filters: dict | None) -> models.Filter | None:
    """Basit dict filtresini Qdrant Filter'ına çevirir (must = AND).

    {"category": "docs"}                    → eşitlik (MatchValue)
    {"extension": [".pdf", ".md"]}          → çoklu değer / OR (MatchAny)
    {"created_at": {"gte": 1700000000}}     → sayısal/tarih aralığı (Range)
    """
    if not filters:
        return None
    conditions: list[models.FieldCondition] = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, dict) and _RANGE_KEYS.issuperset(value.keys()):
            conditions.append(
                models.FieldCondition(
                    key=key,
                    range=models.Range(
                        gt=value.get("gt"),
                        gte=value.get("gte"),
                        lt=value.get("lt"),
                        lte=value.get("lte"),
                    ),
                )
            )
        elif isinstance(value, (list, tuple, set)):
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchAny(any=list(value)))
            )
        else:
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
            )
    return models.Filter(must=conditions) if conditions else None
