"""MCP Server: RAG servisini Model Context Protocol araçları olarak sunar.

Yeni iş mantığı YOK — mevcut `RetrievalService`/`ChatService`'i yeniden kullanır,
yalnızca MCP tool arayüzüne köprü kurar; temel araçların MCP istemcileri
tarafından kullanılabilir olması hedeflenir.

DI, MCP SDK'nın lifespan context mekanizması yerine projenin geri kalanıyla
tutarlı biçimde düz factory fonksiyonlarıyla yapılır (`create_server(...)`):
hem test edilebilirliği kolaylaştırır (fake servislerle çağrılabilir) hem de
FastAPI `dependencies.py`'deki desenle aynı kalır.

Araçlar:
- ``search_documents``: hibrit (dense+BM25) arama, ham chunk'ları döner.
- ``ask_question``: retrieval + LLM ile kaynak atıflı RAG cevabı üretir.

Çalıştırma (stdio transport — MCP destekleyen bir istemci tarafından başlatılır):
    uv run python -m app.mcp.server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.providers.llm.base import LLMProvider
from app.repositories.conversation_repo import ConversationRepository
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService


def create_server(
    settings: Settings,
    retrieval: RetrievalService,
    llm: LLMProvider,
    sessionmaker: async_sessionmaker,
) -> FastMCP:
    """MCP sunucusunu kurar. Servisler dışarıdan enjekte edilir (testte fake'lenebilir)."""
    mcp = FastMCP(
        "ai-knowledge-assistant",
        instructions=(
            "Kurumsal doküman bilgi tabanında arama yapar ve yalnızca yüklenmiş "
            "dokümanlardaki bilgiye dayanan, kaynak gösteren cevaplar üretir."
        ),
    )

    @mcp.tool()
    async def search_documents(
        query: str,
        top_k: int = 5,
        category: str | None = None,
        document_name: str | None = None,
    ) -> list[dict]:
        """Bilgi tabanında hibrit (dense+BM25) arama yapar, ilgili chunk'ları döner."""
        filters: dict = {}
        if category:
            filters["category"] = category
        if document_name:
            filters["document_name"] = document_name
        results = await retrieval.retrieve(query, top_k=top_k, filters=filters or None)
        return [
            {
                "document_name": r.document_name,
                "page": r.page,
                "score": round(r.score, 4),
                "snippet": r.text[:500],
            }
            for r in results
        ]

    @mcp.tool()
    async def ask_question(
        question: str,
        conversation_id: str | None = None,
        top_k: int = 5,
    ) -> dict:
        """Bilgi tabanına dayalı, kaynak atıflı bir RAG cevabı üretir."""
        async with sessionmaker() as session:
            chat = ChatService(settings, retrieval, llm, ConversationRepository(session))
            result = await chat.answer(question, top_k=top_k, conversation_id=conversation_id)
        return {
            "answer": result.answer,
            "citations": [
                {
                    "marker": c.marker,
                    "document_name": c.document_name,
                    "page": c.page,
                    "snippet": c.snippet,
                }
                for c in result.citations
            ],
            "conversation_id": result.conversation_id,
        }

    return mcp


def main() -> None:
    import asyncio

    from app.config import get_settings
    from app.database import get_sessionmaker, init_models
    from app.dependencies import (
        get_embedding_provider,
        get_llm_provider,
        get_sparse_encoder,
        get_vector_store,
    )
    from app.logging import configure_logging

    settings = get_settings()
    configure_logging(settings)

    embedding = get_embedding_provider()
    vector_store = get_vector_store()
    sparse = get_sparse_encoder()
    llm = get_llm_provider()
    retrieval = RetrievalService(settings, embedding, vector_store, sparse)

    asyncio.run(init_models())
    sessionmaker = get_sessionmaker()

    server = create_server(settings, retrieval, llm, sessionmaker)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
