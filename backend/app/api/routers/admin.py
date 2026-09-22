"""Admin Dashboard ucu: doküman/chunk sayısı, indeks durumu, temel metrikler."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.schemas.admin import AdminStatsResponse, ChunkItem, ChunkListResponse
from app.dependencies import (
    ConversationRepositoryDep,
    DocumentRepositoryDep,
    SettingsDep,
    VectorStoreDep,
)
from app.log_stream import recent_logs, subscribe, unsubscribe
from app.observability import get_admin_metrics, get_model_health

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    documents: DocumentRepositoryDep,
    conversations: ConversationRepositoryDep,
    vector_store: VectorStoreDep,
    settings: SettingsDep,
) -> AdminStatsResponse:
    documents_total = await documents.count()
    documents_by_status = await documents.count_by_status()
    chunks_indexed = await vector_store.count()
    conversations_total = await conversations.count()
    metrics = get_admin_metrics()

    return AdminStatsResponse(
        documents_total=documents_total,
        documents_by_status=documents_by_status,
        chunks_indexed=chunks_indexed,
        conversations_total=conversations_total,
        llm_model=settings.llm_model,
        llm_rewrite_model=settings.llm_rewrite_model,
        llm_model_ok=get_model_health(settings.llm_model),
        llm_rewrite_model_ok=get_model_health(settings.llm_rewrite_model),
        **metrics,
    )


@router.get("/chunks", response_model=ChunkListResponse)
async def list_chunks(
    vector_store: VectorStoreDep,
    documents: DocumentRepositoryDep,
    limit: int = 50,
    offset: str | None = None,
    document_id: str | None = None,
) -> ChunkListResponse:
    """İndekslenen chunk'ları listeler (Admin Dashboard'da inceleme için).

    `document_id` verilirse yalnızca o dokümanın **tüm** chunk'ları, dokümandaki
    sıraya (index) göre döner — bir PDF'in nasıl chunk'landığını görmek için. Aksi
    hâlde tüm koleksiyon sayfalı gelir.

    Devre dışı bırakılan dokümanların chunk'ları Qdrant'tan silinmez (bkz.
    `ChatService._exclude_disabled`); burada da gösterilir ama `enabled=False`
    işaretlenir ki hangi chunk'ın cevaplarda kullanılmadığı görülebilsin.
    """
    disabled_ids = await documents.list_disabled_ids()

    def _to_item(p) -> ChunkItem:
        return ChunkItem(
            chunk_id=p.payload.get("chunk_id", p.id),
            document_id=p.payload.get("document_id", ""),
            document_name=p.payload.get("document_name", ""),
            index=p.payload.get("index"),
            text=p.payload.get("text", ""),
            page=p.payload.get("page"),
            enabled=p.payload.get("document_id") not in disabled_ids,
        )

    # Doküman-bazlı: o dokümanın tüm chunk'larını topla, index'e göre sırala.
    if document_id:
        items: list[ChunkItem] = []
        cursor: str | None = None
        while True:
            points, cursor = await vector_store.scroll(
                limit=200, offset=cursor, document_id=document_id
            )
            items.extend(_to_item(p) for p in points)
            if cursor is None:
                break
        items.sort(key=lambda c: c.index if c.index is not None else 0)
        return ChunkListResponse(items=items, next_offset=None)

    # Tümü: sayfalı; her sayfayı doküman + index bazında okunaklı sırala.
    points, next_offset = await vector_store.scroll(limit=limit, offset=offset)
    items = [_to_item(p) for p in points]
    items.sort(key=lambda c: (c.document_name, c.index if c.index is not None else 0))
    return ChunkListResponse(items=items, next_offset=next_offset)


@router.get("/logs/recent")
async def get_recent_logs() -> list[dict[str, Any]]:
    """Sayfa ilk açıldığında geçmişi göstermek için son loglar (ring buffer)."""
    return recent_logs()


@router.get("/logs/stream")
async def stream_logs(request: Request) -> StreamingResponse:
    """Canlı log akışı (SSE) — bir isteğin arka planda hangi adımlardan geçtiğini
    (retrieval, LLM çağrısı, hata vb.) gerçek zamanlı izlemek için."""
    queue = subscribe()

    async def event_source() -> AsyncIterator[str]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(entry, ensure_ascii=False, default=str)}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            unsubscribe(queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
