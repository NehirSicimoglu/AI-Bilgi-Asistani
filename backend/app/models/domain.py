"""Domain modelleri — katmanlar arası paylaşılan çekirdek veri yapıları.

Bunlar framework'ten bağımsız iş nesneleridir. API DTO'ları (`api/schemas`)
ve DB modelleri (`models/db`) ayrıdır; bu modeller servisler ile sağlayıcılar
arasında dolaşır.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Document(BaseModel):
    """Yüklenen bir kaynak doküman."""

    id: str = Field(default_factory=_new_id)
    filename: str
    extension: str  # ".pdf", ".docx", ".txt", ".md"
    category: str | None = None
    size_bytes: int = 0
    num_chunks: int = 0
    status: DocumentStatus = DocumentStatus.PENDING
    error: str | None = None
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class Chunk(BaseModel):
    """Bir dokümandan üretilen, embedding'e ve indekslemeye uygun metin parçası."""

    id: str = Field(default_factory=_new_id)
    document_id: str
    index: int  # doküman içindeki sıra
    text: str
    page: int | None = None
    # Filtreleme/citation için taşınan metadata (doküman adı, kategori, vb.)
    metadata: dict = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Retrieval'dan dönen, skorlu bir chunk sonucu."""

    chunk_id: str
    document_id: str
    document_name: str
    text: str
    score: float
    page: int | None = None
    metadata: dict = Field(default_factory=dict)


class Citation(BaseModel):
    """Cevapta gösterilen kaynak atıfı — retrieval'dan deterministik üretilir."""

    marker: int  # cevap içinde [1], [2] ... ile eşleşen numara
    chunk_id: str
    document_id: str
    document_name: str
    page: int | None = None
    snippet: str = ""
    score: float | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Message(BaseModel):
    """Bir konuşma turundaki tek mesaj (kullanıcı sorusu veya asistan cevabı)."""

    id: str = Field(default_factory=_new_id)
    conversation_id: str
    role: Role
    content: str
    # Asistan mesajlarında cevaba eşlik eden citation'lar (kullanıcıda boş).
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Conversation(BaseModel):
    """Çok turlu bir sohbet oturumu — mesaj geçmişini gruplar."""

    id: str = Field(default_factory=_new_id)
    title: str | None = None
    pinned: bool = False
    project_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Project(BaseModel):
    """Sohbetleri gruplamak için kullanıcı tanımlı bir klasör ("Proje")."""

    id: str = Field(default_factory=_new_id)
    name: str
    created_at: datetime = Field(default_factory=_utcnow)
