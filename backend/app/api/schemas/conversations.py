"""Konuşma (conversation) API DTO'ları."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.chat import CitationSchema
from app.models.domain import Conversation, Message, Role


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=512)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    pinned: bool | None = None
    # `project_id: None` = projeden çıkar; alan hiç gönderilmezse dokunulmaz
    # (bkz. router'da `model_fields_set` kontrolü).
    project_id: str | None = None


class ConversationResponse(BaseModel):
    id: str
    title: str | None = None
    pinned: bool
    project_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, c: Conversation) -> ConversationResponse:
        return cls(
            id=c.id,
            title=c.title,
            pinned=c.pinned,
            project_id=c.project_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )


class ConversationListResponse(BaseModel):
    total: int
    items: list[ConversationResponse]


class MessageResponse(BaseModel):
    id: str
    role: Role
    content: str
    citations: list[CitationSchema]
    created_at: datetime

    @classmethod
    def from_domain(cls, m: Message) -> MessageResponse:
        return cls(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=[CitationSchema.from_domain(c) for c in m.citations],
            created_at=m.created_at,
        )


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]

    @classmethod
    def from_domain_with_messages(
        cls, c: Conversation, messages: list[Message]
    ) -> ConversationDetailResponse:
        return cls(
            id=c.id,
            title=c.title,
            pinned=c.pinned,
            project_id=c.project_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
            messages=[MessageResponse.from_domain(m) for m in messages],
        )
