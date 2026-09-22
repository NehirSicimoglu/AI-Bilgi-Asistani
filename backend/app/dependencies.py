"""Bağımlılık enjeksiyonu (DI) — sağlayıcı/servis fabrikaları.

Ayrı bir DI kütüphanesi yerine sade fabrika fonksiyonları + FastAPI `Depends`
kullanılır (az sihir, kolay test override). Somut sağlayıcılar `.env` ayarına
göre burada seçilir; servisler yalnızca interface'e bağımlıdır.

Sağlayıcı fabrikaları `@lru_cache` ile tekil tutulur (istek başına yeni istemci
açılmaz); repository ve servis fabrikaları ise istek kapsamındaki DB oturumuna
bağlı olduğundan her istekte yeniden kurulur.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.exceptions import AppError
from app.ingestion.sparse import SparseEncoder
from app.providers.embedding.base import EmbeddingProvider
from app.providers.llm.base import LLMProvider
from app.providers.vector_store.base import VectorStore
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.project_repo import ProjectRepository
from app.services.chat import ChatService
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """`.env`'deki `embedding_provider` ayarına göre embedding sağlayıcısını kurar."""
    settings = get_settings()
    provider = settings.embedding_provider.lower()
    if provider == "google":
        from app.providers.embedding.google import GoogleEmbeddingProvider

        return GoogleEmbeddingProvider(settings)
    raise AppError(f"Bilinmeyen embedding sağlayıcısı: {provider}")


EmbeddingDep = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]


@lru_cache
def get_sparse_encoder() -> SparseEncoder:
    """`.env`'deki `sparse_encoder` ayarına göre BM25 seyrek kodlayıcıyı kurar."""
    settings = get_settings()
    encoder = settings.sparse_encoder.lower()
    if encoder == "bm25":
        from app.ingestion.sparse import Bm25SparseEncoder

        return Bm25SparseEncoder()
    raise AppError(f"Bilinmeyen sparse encoder: {encoder}")


SparseEncoderDep = Annotated[SparseEncoder, Depends(get_sparse_encoder)]


@lru_cache
def get_vector_store() -> VectorStore:
    """`.env`'deki `vector_store_provider` ayarına göre vektör deposunu kurar."""
    settings = get_settings()
    provider = settings.vector_store_provider.lower()
    if provider == "qdrant":
        from app.providers.vector_store.qdrant import QdrantVectorStore

        return QdrantVectorStore(settings)
    raise AppError(f"Bilinmeyen vektör deposu sağlayıcısı: {provider}")


VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]


@lru_cache
def get_llm_provider() -> LLMProvider:
    """`.env`'deki `llm_provider` ayarına göre LLM sağlayıcısını kurar."""
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        from app.providers.llm.gemini import GeminiLLMProvider

        return GeminiLLMProvider(settings)
    raise AppError(f"Bilinmeyen LLM sağlayıcısı: {provider}")


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]


def get_document_repository(session: SessionDep) -> DocumentRepository:
    return DocumentRepository(session)


DocumentRepositoryDep = Annotated[DocumentRepository, Depends(get_document_repository)]


def get_conversation_repository(session: SessionDep) -> ConversationRepository:
    return ConversationRepository(session)


ConversationRepositoryDep = Annotated[
    ConversationRepository, Depends(get_conversation_repository)
]


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_ingestion_service(
    settings: SettingsDep,
    embedding: EmbeddingDep,
    vector_store: VectorStoreDep,
    repo: DocumentRepositoryDep,
    sparse: SparseEncoderDep,
) -> IngestionService:
    return IngestionService(settings, embedding, vector_store, repo, sparse)


IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]


def get_retrieval_service(
    settings: SettingsDep,
    embedding: EmbeddingDep,
    vector_store: VectorStoreDep,
    sparse: SparseEncoderDep,
) -> RetrievalService:
    return RetrievalService(settings, embedding, vector_store, sparse)


RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]


def get_chat_service(
    settings: SettingsDep,
    retrieval: RetrievalServiceDep,
    llm: LLMProviderDep,
    conversations: ConversationRepositoryDep,
    documents: DocumentRepositoryDep,
) -> ChatService:
    return ChatService(settings, retrieval, llm, conversations, documents)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
