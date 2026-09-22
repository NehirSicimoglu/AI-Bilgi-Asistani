"""SQLAlchemy (async) ORM modelleri.

PostgreSQL doküman yaşam döngüsünün kaynağıdır (durum, sayaçlar, metadata).
Chunk'ların kendisi ve metinleri Qdrant payload'ında tutulur (retrieval'ın
kaynağı orasıdır); burada tekrar saklamayız, `num_chunks` sayacı yeterlidir.
Konuşma geçmişi (Conversation/Message) da burada tutulur — çok turlu sohbetin
kaynağıdır.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    extension: Mapped[str] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    num_chunks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    messages: Mapped[list[MessageRow]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageRow.created_at",
    )


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # Asistan citation'ları JSON olarak; kullanıcı mesajlarında boş liste.
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    conversation: Mapped[ConversationRow] = relationship(back_populates="messages")
