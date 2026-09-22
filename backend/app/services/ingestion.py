"""Ingestion servisi — bir dokümanı uçtan uca bilgi tabanına alır.

Akış: doğrula → parse → chunk → embed (dense + BM25 sparse) → Qdrant'a indeksle →
durum/metadata'yı Postgres'e yaz. Her chunk hem dense hem sparse vektörle indekslenir;
böylece retrieval'da hybrid (dense + BM25, RRF) yeniden indeksleme gerektirmeden çalışır.
Servis yalnızca interface'lere (EmbeddingProvider, VectorStore, SparseEncoder) ve
repository'ye bağımlıdır; somut sağlayıcıyı bilmez.
"""

from __future__ import annotations

import os

from app.config import Settings
from app.exceptions import UnsupportedFileTypeError, ValidationError
from app.ingestion.chunking import chunk_document
from app.ingestion.parsers import parse_document
from app.ingestion.sparse import SparseEncoder
from app.logging import get_logger
from app.models.domain import Document, DocumentStatus
from app.observability import record_ingestion
from app.providers.embedding.base import EmbeddingProvider
from app.providers.vector_store.base import VectorPoint, VectorStore
from app.repositories.document_repo import DocumentRepository

logger = get_logger(__name__)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        embedding: EmbeddingProvider,
        vector_store: VectorStore,
        repo: DocumentRepository,
        sparse_encoder: SparseEncoder,
    ) -> None:
        self._settings = settings
        self._embedding = embedding
        self._vector_store = vector_store
        self._repo = repo
        self._sparse = sparse_encoder

    def _validate(self, filename: str, data: bytes) -> str:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self._settings.allowed_extensions:
            raise UnsupportedFileTypeError(
                f"Desteklenmeyen dosya türü: {ext or '(uzantısız)'}. "
                f"İzin verilenler: {', '.join(self._settings.allowed_extensions)}"
            )
        max_bytes = self._settings.max_upload_mb * 1024 * 1024
        if len(data) > max_bytes:
            raise ValidationError(
                f"Dosya çok büyük ({len(data)} bayt). "
                f"Üst sınır: {self._settings.max_upload_mb} MB"
            )
        if not data:
            raise ValidationError("Dosya boş.")
        return ext

    async def ingest(
        self, *, filename: str, data: bytes, category: str | None = None
    ) -> Document:
        ext = self._validate(filename, data)

        doc = Document(
            filename=filename,
            extension=ext,
            category=category,
            size_bytes=len(data),
            status=DocumentStatus.PROCESSING,
        )
        await self._repo.add(doc)

        try:
            parsed = parse_document(data, filename, ext)
            base_metadata = {
                "document_id": doc.id,
                "document_name": filename,
                "category": category,
            }
            chunks = chunk_document(
                parsed,
                document_id=doc.id,
                chunk_size=self._settings.chunk_size,
                chunk_overlap=self._settings.chunk_overlap,
                base_metadata=base_metadata,
            )
            if not chunks:
                raise ValidationError("Dokümandan metin çıkarılamadı.")

            texts = [c.text for c in chunks]
            vectors = await self._embedding.embed_texts(texts)
            sparse_vectors = self._sparse.encode_batch(texts)
            points = [
                VectorPoint(
                    id=chunk.id,
                    dense=vector,
                    sparse=sparse,
                    payload={
                        "chunk_id": chunk.id,
                        "document_id": doc.id,
                        "document_name": filename,
                        "category": category,
                        "extension": doc.extension,  # tür filtresi (.pdf/.docx/...)
                        "created_at": doc.created_at.timestamp(),  # tarih aralığı filtresi
                        "page": chunk.page,
                        "index": chunk.index,
                        "text": chunk.text,
                    },
                )
                for chunk, vector, sparse in zip(
                    chunks, vectors, sparse_vectors, strict=True
                )
            ]

            await self._vector_store.ensure_collection()
            await self._vector_store.upsert(points)

            doc.num_chunks = len(chunks)
            doc.status = DocumentStatus.INDEXED
            await self._repo.update(doc)
            record_ingestion(len(chunks))
            logger.info(
                "document_ingested",
                document_id=doc.id,
                filename=filename,
                chunks=len(chunks),
            )
        except Exception as exc:
            doc.status = DocumentStatus.FAILED
            doc.error = str(exc)
            await self._repo.update(doc)
            logger.error("ingestion_failed", document_id=doc.id, error=str(exc))
            raise

        return doc

    async def delete(self, document_id: str) -> bool:
        deleted = await self._repo.delete(document_id)
        if deleted:
            await self._vector_store.delete_by_document(document_id)
        return deleted
