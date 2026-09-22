"""Admin Dashboard API DTO'su."""

from __future__ import annotations

from pydantic import BaseModel


class AdminStatsResponse(BaseModel):
    documents_total: int
    documents_by_status: dict[str, int]
    chunks_indexed: int
    conversations_total: int
    chat_requests_total: int
    avg_chat_latency_ms: float | None
    total_llm_tokens: int
    llm_model: str
    llm_rewrite_model: str
    llm_model_ok: bool | None
    llm_rewrite_model_ok: bool | None


class ChunkItem(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    index: int | None = None  # dokümandaki sıra (0,1,2… — PDF sırası)
    text: str
    page: int | None = None
    enabled: bool = True


class ChunkListResponse(BaseModel):
    items: list[ChunkItem]
    next_offset: str | None = None
