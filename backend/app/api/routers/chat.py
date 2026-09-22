"""Chat ucu — RAG cevabı + citation (non-streaming `/chat` ve SSE streaming `/chat/stream`).

`conversation_id` verilirse çok turlu sohbet devreye girer. Konuşmanın var olduğu
her iki uçta da AKIŞ BAŞLAMADAN doğrulanır; böylece bilinmeyen konuşma streaming
sırasında değil, düzgün bir 404 ile reddedilir.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas.chat import ChatRequest, ChatResponse
from app.api.sse import sse_stream
from app.dependencies import ChatServiceDep, ConversationRepositoryDep
from app.exceptions import NotFoundError

router = APIRouter(tags=["chat"])


async def _ensure_conversation(
    conversation_id: str | None, conversations: ConversationRepositoryDep
) -> None:
    if conversation_id and not await conversations.exists(conversation_id):
        raise NotFoundError("Konuşma bulunamadı.")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    service: ChatServiceDep,
    conversations: ConversationRepositoryDep,
) -> ChatResponse:
    await _ensure_conversation(req.conversation_id, conversations)
    result = await service.answer(
        req.query,
        top_k=req.top_k,
        mode=req.mode,
        filters=req.filter.to_filters() if req.filter else None,
        conversation_id=req.conversation_id,
    )
    return ChatResponse.from_result(result)


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    service: ChatServiceDep,
    conversations: ConversationRepositoryDep,
) -> StreamingResponse:
    """RAG cevabını SSE ile akıtır: `sources` → `token`* → `citations`."""
    await _ensure_conversation(req.conversation_id, conversations)
    events = service.stream_answer(
        req.query,
        top_k=req.top_k,
        mode=req.mode,
        filters=req.filter.to_filters() if req.filter else None,
        conversation_id=req.conversation_id,
    )
    return StreamingResponse(
        sse_stream(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
