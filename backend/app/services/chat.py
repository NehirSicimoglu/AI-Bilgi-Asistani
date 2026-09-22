"""Chat servisi — RAG cevabı + citation üretir (streaming ve non-streaming).

Akış: (varsa geçmişe göre sorguyu yeniden yaz) → retrieve → numaralı bağlam kur →
LLM'e sor → cevaptaki [n] işaretlerinden citation'ları eşle. Kaynaklar deterministik
(retrieval'dan) geldiği için citation LLM'in serbest metnine güvenmez; yalnızca
hangi numaraya atıf yapıldığını okur.

Çok turlu sohbet: `conversation_id` verildiğinde konuşma geçmişi
yüklenir, takip soruları geçmişe duyarlı biçimde bağımsız sorguya çevrilir
(history-aware query rewriting) ve tur (kullanıcı + asistan mesajı) kalıcı olarak
saklanır. `conversation_id` yoksa servis eskisi gibi durumsuz (stateless) çalışır.

Streaming'de (`stream_answer`) kaynak listesi retrieval'dan BAŞTAN gönderilir; LLM
token'ları akarken kesin citation henüz bilinmez, bu yüzden akış bittiğinde cevabın
tamamındaki [n] işaretlerinden nihai citation'lar hesaplanıp son event olarak
yollanır. Servis transport'tan bağımsızdır: SSE'yi bilmez, yapısal event üretir.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field

from app.config import Settings
from app.exceptions import ProviderError
from app.logging import get_logger
from app.models.domain import Citation, Message, RetrievalResult, Role, TokenUsage
from app.observability import observe_chat, record_llm_usage
from app.providers.llm.base import LLMMessage, LLMProvider
from app.providers.vector_store.base import SearchMode
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.document_repo import DocumentRepository
from app.services.prompts import (
    DECOMPOSE_SYSTEM_PROMPT,
    NO_CONTEXT_ANSWER,
    REWRITE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_context,
    build_decompose_prompt,
    build_rewrite_prompt,
    build_user_prompt,
)
from app.services.retrieval import RetrievalService

logger = get_logger(__name__)

_MARKER_RE = re.compile(r"\[(\d+)\]")
_SNIPPET_LEN = 240


class ChatResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    usage: TokenUsage = TokenUsage()
    conversation_id: str | None = None


class StreamEvent(BaseModel):
    """Transport'tan bağımsız akış olayı; API katmanı bunu SSE'ye serialize eder.

    event türleri:
    - ``sources``: retrieval'dan gelen aday kaynaklar (baştan, tek sefer).
    - ``token``: cevabın bir parçası (birden çok kez).
    - ``citations``: cevapta gerçekten atıf yapılan kaynaklar (akış sonu).
    - ``error``: akış sırasında hata.
    """

    event: str
    data: dict = Field(default_factory=dict)


class ChatService:
    def __init__(
        self,
        settings: Settings,
        retrieval: RetrievalService,
        llm: LLMProvider,
        conversation_repo: ConversationRepository | None = None,
        document_repo: DocumentRepository | None = None,
    ) -> None:
        self._settings = settings
        self._retrieval = retrieval
        self._llm = llm
        self._conversations = conversation_repo
        self._documents = document_repo

    async def answer(
        self,
        query: str,
        *,
        top_k: int | None = None,
        mode: SearchMode | None = None,
        filters: dict | None = None,
        conversation_id: str | None = None,
    ) -> ChatResult:
        start = time.perf_counter()
        history = await self._load_history(conversation_id)
        search_query = await self._rewrite_query(history, query)
        results = await self._run_retrieval(
            search_query, top_k=top_k, mode=mode, filters=filters
        )
        results = await self._exclude_disabled(results)

        if not results:
            await self._persist_turn(conversation_id, query, NO_CONTEXT_ANSWER, [])
            observe_chat(time.perf_counter() - start)
            return ChatResult(
                answer=NO_CONTEXT_ANSWER, conversation_id=conversation_id
            )

        context = build_context(results)
        messages = _build_messages(history, query, context)
        response = await self._llm.generate(messages, system=SYSTEM_PROMPT)

        # Citation'lar ham metindeki [n] işaretlerinden hesaplanır; ardından
        # işaretler kullanıcıya gösterilecek/saklanacak metinden temizlenir.
        citations = _build_citations(response.text, results)
        answer = _strip_markers(response.text)
        await self._persist_turn(conversation_id, query, answer, citations)
        record_llm_usage(response.usage)
        observe_chat(time.perf_counter() - start)
        logger.info(
            "chat_answered",
            query_len=len(query),
            rewritten=search_query != query,
            sources=len(results),
            cited=len(citations),
            total_tokens=response.usage.total_tokens,
        )
        return ChatResult(
            answer=answer,
            citations=citations,
            usage=response.usage,
            conversation_id=conversation_id,
        )

    async def stream_answer(
        self,
        query: str,
        *,
        top_k: int | None = None,
        mode: SearchMode | None = None,
        filters: dict | None = None,
        conversation_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """RAG cevabını parça parça (SSE için) üretir.

        Sıra: ``sources`` (baştan) → ``token`` (çok) → ``citations`` (sonda).
        Boş bilgi tabanında tek ``token`` + boş ``citations`` yollar.
        Konuşma verildiyse kullanıcı sorusu baştan, asistan cevabı akış bitince
        kalıcı olarak yazılır.
        """
        start = time.perf_counter()
        logger.info(
            "chat_pipeline_started",
            query_len=len(query),
            has_history=bool(conversation_id),
        )
        history = await self._load_history(conversation_id)
        search_query = await self._rewrite_query(history, query)
        if search_query != query:
            logger.info("query_rewritten", original=query, rewritten=search_query)
        results = await self._run_retrieval(
            search_query, top_k=top_k, mode=mode, filters=filters
        )
        results = await self._exclude_disabled(results)

        await self._persist_message(conversation_id, Role.USER, query, [])

        if not results:
            yield StreamEvent(event="token", data={"text": NO_CONTEXT_ANSWER})
            yield StreamEvent(event="citations", data={"citations": []})
            await self._persist_message(
                conversation_id, Role.ASSISTANT, NO_CONTEXT_ANSWER, []
            )
            return

        # Kaynakları baştan gönder — LLM token'ları akmadan önce panel dolabilir.
        yield StreamEvent(
            event="sources",
            data={"sources": [_source_payload(i, r) for i, r in enumerate(results, 1)]},
        )

        context = build_context(results)
        messages = _build_messages(history, query, context)
        parts: list[str] = []  # ham parçalar (işaretler dahil) — citation için
        stripper = _MarkerStripper()  # kullanıcıya gösterilen metin — işaretsiz
        logger.info("llm_stream_started", model=self._settings.llm_model, sources=len(results))
        try:
            async for piece in self._llm.stream(messages, system=SYSTEM_PROMPT):
                parts.append(piece)
                visible = stripper.feed(piece)
                if visible:
                    yield StreamEvent(event="token", data={"text": visible})
        except ProviderError as exc:
            logger.error("chat_stream_failed", error=str(exc))
            yield StreamEvent(event="error", data={"message": str(exc)})
            return

        tail = stripper.flush()
        if tail:
            yield StreamEvent(event="token", data={"text": tail})

        raw_answer = "".join(parts)
        citations = _build_citations(raw_answer, results)
        answer = _strip_markers(raw_answer)
        await self._persist_message(
            conversation_id, Role.ASSISTANT, answer, citations
        )
        observe_chat(time.perf_counter() - start)
        logger.info(
            "chat_streamed",
            query_len=len(query),
            rewritten=search_query != query,
            sources=len(results),
            cited=len(citations),
        )
        yield StreamEvent(
            event="citations",
            data={"citations": [c.model_dump() for c in citations]},
        )

    async def _exclude_disabled(
        self, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """Devre dışı bırakılan dokümanlara ait chunk'ları cevaptan hariç tutar."""
        if self._documents is None or not results:
            return results
        disabled_ids = await self._documents.list_disabled_ids()
        if not disabled_ids:
            return results
        return [r for r in results if r.document_id not in disabled_ids]

    # --- Konuşma belleği yardımcıları ------------------------------------------

    async def _load_history(self, conversation_id: str | None) -> list[Message]:
        if not conversation_id or self._conversations is None:
            return []
        return await self._conversations.get_messages(
            conversation_id, limit=self._settings.chat_history_messages
        )

    async def _rewrite_query(self, history: list[Message], query: str) -> str:
        """Takip sorusunu geçmişe göre bağımsız sorguya çevirir.

        Geçmiş yoksa soru aynen kullanılır. Yeniden yazım başarısız/boş olursa
        (LLM hatası) özgün soruya güvenle geri dönülür — bellek retrieval'ı bloke etmez.
        """
        if not history:
            return query
        logger.info("query_rewrite_started", model=self._settings.llm_rewrite_model)
        messages = [
            LLMMessage(role=Role.USER, content=build_rewrite_prompt(history, query))
        ]
        try:
            resp = await self._llm.generate(
                messages,
                system=REWRITE_SYSTEM_PROMPT,
                model=self._settings.llm_rewrite_model,
            )
        except ProviderError as exc:
            logger.warning("query_rewrite_failed", error=str(exc))
            return query
        return resp.text.strip() or query

    async def _decompose_query(self, query: str) -> list[str]:
        """Çok-belgeli soruyu bağımsız alt-sorgulara böler (multi-query retrieval).

        Bayrak kapalıysa veya bölme başarısız/tek satır olursa güvenle ``[query]``
        döner — decomposition retrieval'ı asla bloke etmez, yalnızca kapsamı genişletir.
        En fazla ``decomposition_max_subqueries`` alt-sorgu döndürülür; tekrar edenler
        elenir ve özgün soru bölünmediyse tek elemanlı liste verilir.
        """
        if not self._settings.enable_query_decomposition:
            return [query]
        max_n = self._settings.decomposition_max_subqueries
        logger.info("query_decompose_started", model=self._settings.llm_rewrite_model)
        system = DECOMPOSE_SYSTEM_PROMPT.format(max_subqueries=max_n)
        messages = [
            LLMMessage(role=Role.USER, content=build_decompose_prompt(query, max_n))
        ]
        try:
            resp = await self._llm.generate(
                messages,
                system=system,
                model=self._settings.llm_rewrite_model,
            )
        except ProviderError as exc:
            logger.warning("query_decompose_failed", error=str(exc))
            return [query]
        subqueries = _parse_subqueries(resp.text, max_n)
        if not subqueries:
            return [query]
        logger.info("query_decomposed", original=query, subqueries=subqueries)
        return subqueries

    async def _run_retrieval(
        self,
        search_query: str,
        *,
        top_k: int | None,
        mode: SearchMode | None,
        filters: dict | None,
    ) -> list[RetrievalResult]:
        """Sorguyu getirir; decomposition açık ve soru bölünüyorsa çoklu-sorgu yolu.

        Bölme tek alt-sorgu döndürürse (bayrak kapalı, tek bilgi ihtiyacı veya
        fallback) davranış eskisiyle birebir aynıdır: normal ``retrieve`` + ``top_k``.
        Birden çok alt-sorguda ``retrieve_multi`` (alt-sorgu başına ``subquery_top_k``)
        kullanılır.
        """
        subqueries = await self._decompose_query(search_query)
        if len(subqueries) > 1:
            return await self._retrieval.retrieve_multi(
                subqueries, mode=mode, filters=filters
            )
        return await self._retrieval.retrieve(
            search_query, top_k=top_k, mode=mode, filters=filters
        )

    async def _persist_turn(
        self,
        conversation_id: str | None,
        query: str,
        answer: str,
        citations: list[Citation],
    ) -> None:
        await self._persist_message(conversation_id, Role.USER, query, [])
        await self._persist_message(
            conversation_id, Role.ASSISTANT, answer, citations
        )

    async def _persist_message(
        self,
        conversation_id: str | None,
        role: Role,
        content: str,
        citations: list[Citation],
    ) -> None:
        if not conversation_id or self._conversations is None:
            return
        await self._conversations.add_message(
            Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                citations=citations,
            )
        )


def _build_messages(
    history: list[Message], query: str, context: str
) -> list[LLMMessage]:
    """Geçmiş turları + bağlamlı son soruyu LLM mesaj listesine çevirir."""
    messages = [LLMMessage(role=m.role, content=m.content) for m in history]
    messages.append(LLMMessage(role=Role.USER, content=build_user_prompt(query, context)))
    return messages


def _source_payload(marker: int, r: RetrievalResult) -> dict:
    return {
        "marker": marker,
        "chunk_id": r.chunk_id,
        "document_id": r.document_id,
        "document_name": r.document_name,
        "page": r.page,
        "snippet": r.text[:_SNIPPET_LEN],
        "score": r.score,
    }


def _result_to_citation(marker: int, r: RetrievalResult) -> Citation:
    return Citation(
        marker=marker,
        chunk_id=r.chunk_id,
        document_id=r.document_id,
        document_name=r.document_name,
        page=r.page,
        snippet=r.text[:_SNIPPET_LEN],
        score=r.score,
    )


def _build_citations(answer: str, results: list[RetrievalResult]) -> list[Citation]:
    """Cevaptaki [n] işaretlerini retrieval sonuçlarına eşler.

    LLM işaret koymadıysa (ör. tek cümlelik cevap veya talimatı atlaması) kaynak
    paneli boş kalmasın diye retrieval'dan gelen tüm sonuçlara geri düşülür.
    """
    used = sorted({int(m) for m in _MARKER_RE.findall(answer)})
    citations = [
        _result_to_citation(n, results[n - 1])
        for n in used
        if 1 <= n <= len(results)
    ]
    if citations:
        return citations
    # Fallback: hiç geçerli işaret yok → cevaba temel oluşturan kaynakları göster.
    return [_result_to_citation(i, r) for i, r in enumerate(results, start=1)]


# Bölme çıktısındaki satır başı numara/madde işaretlerini temizler: "1) ", "- ", "* ".
_LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s*")


def _parse_subqueries(text: str, max_n: int) -> list[str]:
    """LLM bölme çıktısını temiz alt-sorgu listesine çevirir.

    Her satır bir alt-sorgudur; olası madde işaretleri ("1) ", "- ") ayıklanır,
    boşlar ve tekrar edenler (sıra korunarak) elenir, en fazla ``max_n`` alınır.
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        q = _LIST_PREFIX_RE.sub("", line).strip()
        key = q.casefold()
        if q and key not in seen:
            seen.add(key)
            out.append(q)
        if len(out) >= max_n:
            break
    return out


# İşareti önündeki boşlukla birlikte siler: "bilgi [1] var" -> "bilgi var".
_MARKER_STRIP_RE = re.compile(r"\s*\[\d+\]")


def _strip_markers(text: str) -> str:
    """Kullanıcıya gösterilecek metinden [n] kaynak işaretlerini temizler."""
    cleaned = _MARKER_STRIP_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


class _MarkerStripper:
    """Streaming'de [n] işaretlerini token sınırına takılmadan temizler.

    İki tür belirsizliği tamponda bekletir: (1) birden çok token'a bölünmüş yarım
    işaret ("[", "[1"), (2) ardından işaret gelip gelmeyeceği henüz bilinmeyen
    sondaki boşluk. Böylece işaretten önceki boşluk çift kalmadan yutulabilir.
    """

    _HOLD_RE = re.compile(r"(\s*\[\d*|\s+)$")

    def __init__(self) -> None:
        self._carry = ""

    def feed(self, piece: str) -> str:
        text = _MARKER_STRIP_RE.sub("", self._carry + piece)
        hold = self._HOLD_RE.search(text)
        if hold:
            self._carry = text[hold.start() :]
            return text[: hold.start()]
        self._carry = ""
        return text

    def flush(self) -> str:
        out, self._carry = self._carry, ""
        return out
