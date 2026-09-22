"""Konuşma repository — Conversation/Message (DB) ile domain modelleri arasında köprü.

Çok turlu sohbetin kalıcı kaynağı burasıdır: konuşma oluşturma, mesaj ekleme
(kullanıcı + asistan), geçmiş okuma. Citation'lar mesajda JSON olarak saklanır.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ConversationRow, MessageRow
from app.models.domain import Citation, Conversation, Message, Role


def _conv_to_domain(row: ConversationRow) -> Conversation:
    return Conversation(
        id=row.id,
        title=row.title,
        pinned=row.pinned,
        project_id=row.project_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _msg_to_domain(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        role=Role(row.role),
        content=row.content,
        citations=[Citation(**c) for c in (row.citations or [])],
        created_at=row.created_at,
    )


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, conversation: Conversation) -> Conversation:
        row = ConversationRow(
            id=conversation.id,
            title=conversation.title,
            pinned=conversation.pinned,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        self._session.add(row)
        await self._session.commit()
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        row = await self._session.get(ConversationRow, conversation_id)
        return _conv_to_domain(row) if row else None

    async def rename(self, conversation_id: str, title: str) -> Conversation | None:
        """Başlığı ayarlar (frontend'de kenar çubuğu için, örn. ilk mesajdan otomatik)."""
        row = await self._session.get(ConversationRow, conversation_id)
        if row is None:
            return None
        row.title = title
        await self._session.commit()
        return _conv_to_domain(row)

    async def set_pinned(self, conversation_id: str, pinned: bool) -> Conversation | None:
        row = await self._session.get(ConversationRow, conversation_id)
        if row is None:
            return None
        row.pinned = pinned
        await self._session.commit()
        return _conv_to_domain(row)

    async def set_project(
        self, conversation_id: str, project_id: str | None
    ) -> Conversation | None:
        """Sohbeti bir projeye taşır (`None` verilirse projeden çıkarır)."""
        row = await self._session.get(ConversationRow, conversation_id)
        if row is None:
            return None
        row.project_id = project_id
        await self._session.commit()
        return _conv_to_domain(row)

    async def exists(self, conversation_id: str) -> bool:
        stmt = select(ConversationRow.id).where(ConversationRow.id == conversation_id)
        return (await self._session.scalar(stmt)) is not None

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Conversation]:
        stmt = (
            select(ConversationRow)
            .order_by(ConversationRow.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [_conv_to_domain(r) for r in rows]

    async def count(self) -> int:
        return (await self._session.scalar(select(func.count(ConversationRow.id)))) or 0

    async def delete(self, conversation_id: str) -> bool:
        row = await self._session.get(ConversationRow, conversation_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True

    async def add_message(self, message: Message) -> Message:
        """Mesajı ekler ve ait olduğu konuşmanın `updated_at` alanını tazeler."""
        row = MessageRow(
            id=message.id,
            conversation_id=message.conversation_id,
            role=str(message.role),
            content=message.content,
            citations=[c.model_dump() for c in message.citations],
            created_at=message.created_at,
        )
        self._session.add(row)
        conv = await self._session.get(ConversationRow, message.conversation_id)
        if conv is not None:
            conv.updated_at = message.created_at
        await self._session.commit()
        return message

    async def get_messages(
        self, conversation_id: str, *, limit: int | None = None
    ) -> list[Message]:
        """Konuşmanın mesajlarını kronolojik (eskiden yeniye) döner.

        `limit` verilirse en son `limit` mesaj alınır ama yine kronolojik sırada
        döndürülür (query rewriting/prompt için son N tur).
        """
        stmt = select(MessageRow).where(
            MessageRow.conversation_id == conversation_id
        )
        if limit is not None:
            stmt = stmt.order_by(MessageRow.created_at.desc()).limit(limit)
            rows = list((await self._session.scalars(stmt)).all())
            rows.reverse()
        else:
            stmt = stmt.order_by(MessageRow.created_at.asc())
            rows = list((await self._session.scalars(stmt)).all())
        return [_msg_to_domain(r) for r in rows]
