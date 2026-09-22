"""Doküman API DTO'ları."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.domain import Document, DocumentStatus


class DocumentResponse(BaseModel):
    id: str
    filename: str
    extension: str
    category: str | None
    size_bytes: int
    num_chunks: int
    status: DocumentStatus
    error: str | None
    enabled: bool
    created_at: datetime

    @classmethod
    def from_domain(cls, doc: Document) -> DocumentResponse:
        return cls(
            id=doc.id,
            filename=doc.filename,
            extension=doc.extension,
            category=doc.category,
            size_bytes=doc.size_bytes,
            num_chunks=doc.num_chunks,
            status=doc.status,
            error=doc.error,
            enabled=doc.enabled,
            created_at=doc.created_at,
        )


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentResponse]


class DocumentUpdate(BaseModel):
    enabled: bool
