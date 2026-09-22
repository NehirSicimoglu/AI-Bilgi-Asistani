"""Konuşma belleği: repository + servis (rewriting + persistence), ağsız.

Not: Cross-session görünürlük SQLite :memory:'de garanti olmadığından servis
testleri TEK bir ConversationRepository (tek session) üzerinden çalışır: seed +
sohbet + geri okuma aynı bağlantıda olur. Uçtan uca kalıcılık, StaticPool kullanan
`client` fixture'ı ile `test_conversations_api.py`'de doğrulanır.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ingestion.sparse import Bm25SparseEncoder
from app.models.domain import Conversation, Message, Role
from app.providers.llm.base import LLMResponse
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.document_repo import DocumentRepository
from app.services.chat import ChatService
from app.services.ingestion import IngestionService
from app.services.prompts import REWRITE_SYSTEM_PROMPT
from app.services.retrieval import RetrievalService
from tests.conftest import FakeLLM


class RecordingLLM:
    """Rewrite ve answer çağrılarını ayırır; rewrite girişlerini kaydeder."""

    def __init__(self) -> None:
        self.rewrite_inputs: list[str] = []

    async def generate(
        self, messages, *, system=None, temperature=None, max_tokens=None, model=None
    ):
        from app.models.domain import TokenUsage

        if system == REWRITE_SYSTEM_PROMPT:
            self.rewrite_inputs.append(messages[-1].content)
            return LLMResponse(text="Qdrant nedir", usage=TokenUsage())
        return LLMResponse(text="Cevap [1].", usage=TokenUsage(total_tokens=15))

    async def stream(self, messages, *, system=None, temperature=None, max_tokens=None):
        for piece in "Cevap [1].".split(" "):
            yield piece + " "


async def _seed_corpus(test_settings, fake_embedding, vector_store, sessionmaker) -> None:
    repo = DocumentRepository(sessionmaker())
    ing = IngestionService(test_settings, fake_embedding, vector_store, repo, Bm25SparseEncoder())
    await ing.ingest(
        filename="qdrant.txt",
        data=b"Qdrant bir vektor veritabanidir. " * 30,
        category="db",
    )


# --- Repository -----------------------------------------------------------------


async def test_repo_create_get_exists_delete(sessionmaker) -> None:
    repo = ConversationRepository(sessionmaker())
    conv = await repo.create(Conversation(title="Test"))

    got = await repo.get(conv.id)
    assert got is not None and got.title == "Test"
    assert await repo.exists(conv.id) is True
    assert await repo.exists("yok") is False
    assert await repo.count() == 1

    assert await repo.delete(conv.id) is True
    assert await repo.get(conv.id) is None
    assert await repo.delete(conv.id) is False


async def test_repo_rename(sessionmaker) -> None:
    repo = ConversationRepository(sessionmaker())
    conv = await repo.create(Conversation())

    renamed = await repo.rename(conv.id, "Qdrant nedir?")
    assert renamed is not None and renamed.title == "Qdrant nedir?"
    assert (await repo.get(conv.id)).title == "Qdrant nedir?"
    assert await repo.rename("yok", "x") is None


async def test_repo_messages_order_and_limit(sessionmaker) -> None:
    repo = ConversationRepository(sessionmaker())
    conv = await repo.create(Conversation())
    base = datetime(2026, 7, 17, tzinfo=UTC)
    for i in range(3):
        await repo.add_message(
            Message(
                conversation_id=conv.id,
                role=Role.USER,
                content=f"soru {i}",
                created_at=base + timedelta(seconds=i),
            )
        )

    msgs = await repo.get_messages(conv.id)
    assert [m.content for m in msgs] == ["soru 0", "soru 1", "soru 2"]

    last2 = await repo.get_messages(conv.id, limit=2)
    assert [m.content for m in last2] == ["soru 1", "soru 2"]


async def test_repo_add_message_bumps_updated_at(sessionmaker) -> None:
    repo = ConversationRepository(sessionmaker())
    conv = await repo.create(Conversation())
    later = datetime(2027, 1, 1, tzinfo=UTC)
    await repo.add_message(
        Message(
            conversation_id=conv.id,
            role=Role.USER,
            content="merhaba",
            created_at=later,
        )
    )
    refreshed = await repo.get(conv.id)
    assert refreshed is not None
    # SQLite tz bilgisini düşürür (naive döner); Postgres'te tz korunur. Değeri
    # tz'den bağımsız karşılaştır.
    assert refreshed.updated_at.replace(tzinfo=None) == later.replace(tzinfo=None)


async def test_repo_citations_roundtrip(sessionmaker) -> None:
    from app.models.domain import Citation

    repo = ConversationRepository(sessionmaker())
    conv = await repo.create(Conversation())
    await repo.add_message(
        Message(
            conversation_id=conv.id,
            role=Role.ASSISTANT,
            content="Cevap [1].",
            citations=[
                Citation(marker=1, chunk_id="c1", document_id="d1", document_name="a.txt")
            ],
        )
    )
    msgs = await repo.get_messages(conv.id)
    assert msgs[0].citations[0].document_name == "a.txt"
    assert msgs[0].citations[0].marker == 1


# --- Servis (bellek + rewriting + persistence) ----------------------------------


async def test_chat_rewrites_only_with_history_and_persists(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _seed_corpus(test_settings, fake_embedding, vector_store, sessionmaker)
    conv_repo = ConversationRepository(sessionmaker())
    conv = await conv_repo.create(Conversation())

    llm = RecordingLLM()
    retrieval = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    service = ChatService(test_settings, retrieval, llm, conv_repo)

    r1 = await service.answer("Qdrant nedir?", conversation_id=conv.id, top_k=3)
    assert r1.conversation_id == conv.id
    assert llm.rewrite_inputs == []  # geçmiş yoktu → rewrite yapılmadı

    r2 = await service.answer("peki ya o?", conversation_id=conv.id, top_k=3)
    assert r2.conversation_id == conv.id
    assert len(llm.rewrite_inputs) == 1  # geçmiş vardı → rewrite yapıldı
    assert "peki ya o?" in llm.rewrite_inputs[0]

    msgs = await conv_repo.get_messages(conv.id)
    assert [m.role for m in msgs] == [
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
        Role.ASSISTANT,
    ]
    assert msgs[0].content == "Qdrant nedir?"
    assert msgs[3].citations  # asistanın citation'ı kaydedildi


async def test_chat_without_conversation_is_stateless(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _seed_corpus(test_settings, fake_embedding, vector_store, sessionmaker)
    conv_repo = ConversationRepository(sessionmaker())
    retrieval = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    service = ChatService(test_settings, retrieval, FakeLLM("Yanit [1]."), conv_repo)

    result = await service.answer("vektor veritabani", top_k=3)  # conversation_id yok
    assert result.conversation_id is None
    assert await conv_repo.count() == 0  # hiçbir şey saklanmadı


async def test_stream_persists_user_and_assistant(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    await _seed_corpus(test_settings, fake_embedding, vector_store, sessionmaker)
    conv_repo = ConversationRepository(sessionmaker())
    conv = await conv_repo.create(Conversation())
    retrieval = RetrievalService(test_settings, fake_embedding, vector_store, Bm25SparseEncoder())
    service = ChatService(test_settings, retrieval, FakeLLM("Yanit [1]."), conv_repo)

    events = [
        e
        async for e in service.stream_answer(
            "vektor veritabani", conversation_id=conv.id, top_k=3
        )
    ]
    kinds = [e.event for e in events]
    assert kinds[0] == "sources"
    assert kinds[-1] == "citations"

    msgs = await conv_repo.get_messages(conv.id)
    assert [m.role for m in msgs] == [Role.USER, Role.ASSISTANT]
    assert msgs[0].content == "vektor veritabani"
    assert msgs[1].citations
