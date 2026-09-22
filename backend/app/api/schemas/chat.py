"""Chat API DTO'ları."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.schemas.filters import MetadataFilter
from app.models.domain import Citation, TokenUsage
from app.providers.vector_store.base import SearchMode
from app.services.chat import ChatResult


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)
    mode: SearchMode | None = None
    # Yapılandırılmış metadata filtresi: kategori/tür/tarih aralığı vb.
    filter: MetadataFilter | None = None
    # Verilirse çok turlu sohbet: geçmiş yüklenir, tur kalıcı olarak saklanır.
    conversation_id: str | None = None


class CitationSchema(BaseModel):
    marker: int
    chunk_id: str
    document_id: str
    document_name: str
    page: int | None = None
    snippet: str = ""
    score: float | None = None

    @classmethod
    def from_domain(cls, c: Citation) -> CitationSchema:
        return cls(
            marker=c.marker,
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            document_name=c.document_name,
            page=c.page,
            snippet=c.snippet,
            score=c.score,
        )


class UsageSchema(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    @classmethod
    def from_domain(cls, u: TokenUsage) -> UsageSchema:
        return cls(
            prompt_tokens=u.prompt_tokens,
            completion_tokens=u.completion_tokens,
            total_tokens=u.total_tokens,
        )


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationSchema]
    usage: UsageSchema
    conversation_id: str | None = None

    @classmethod
    def from_result(cls, result: ChatResult) -> ChatResponse:
        return cls(
            answer=result.answer,
            citations=[CitationSchema.from_domain(c) for c in result.citations],
            usage=UsageSchema.from_domain(result.usage),
            conversation_id=result.conversation_id,
        )
