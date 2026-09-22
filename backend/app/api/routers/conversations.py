"""Konuşma uçları: oluşturma, listeleme, geçmiş görüntüleme, silme.

Çok turlu sohbetin yönetim yüzeyi. Sohbetin kendisi `/chat` uçlarında bu
`conversation_id` ile sürer; burada konuşma kaydı ve mesaj geçmişi yönetilir.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.conversations import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)
from app.dependencies import ConversationRepositoryDep
from app.exceptions import NotFoundError
from app.models.domain import Conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    req: ConversationCreate, repo: ConversationRepositoryDep
) -> ConversationResponse:
    conv = await repo.create(Conversation(title=req.title))
    return ConversationResponse.from_domain(conv)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    repo: ConversationRepositoryDep, limit: int = 100, offset: int = 0
) -> ConversationListResponse:
    items = await repo.list(limit=limit, offset=offset)
    total = await repo.count()
    return ConversationListResponse(
        total=total, items=[ConversationResponse.from_domain(c) for c in items]
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str, repo: ConversationRepositoryDep
) -> ConversationDetailResponse:
    conv = await repo.get(conversation_id)
    if conv is None:
        raise NotFoundError("Konuşma bulunamadı.")
    messages = await repo.get_messages(conversation_id)
    return ConversationDetailResponse.from_domain_with_messages(conv, messages)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str, req: ConversationUpdate, repo: ConversationRepositoryDep
) -> ConversationResponse:
    conv = await repo.get(conversation_id)
    if conv is None:
        raise NotFoundError("Konuşma bulunamadı.")
    fields = req.model_fields_set
    if "title" in fields and req.title is not None:
        conv = await repo.rename(conversation_id, req.title)
    if "pinned" in fields and req.pinned is not None:
        conv = await repo.set_pinned(conversation_id, req.pinned)
    if "project_id" in fields:
        conv = await repo.set_project(conversation_id, req.project_id)
    assert conv is not None
    return ConversationResponse.from_domain(conv)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str, repo: ConversationRepositoryDep
) -> None:
    deleted = await repo.delete(conversation_id)
    if not deleted:
        raise NotFoundError("Konuşma bulunamadı.")
