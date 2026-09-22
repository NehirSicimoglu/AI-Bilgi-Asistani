"""Doküman uçları: yükleme, listeleme, görüntüleme, silme."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.api.schemas.documents import DocumentListResponse, DocumentResponse, DocumentUpdate
from app.dependencies import DocumentRepositoryDep, IngestionServiceDep
from app.exceptions import NotFoundError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    service: IngestionServiceDep,
    file: Annotated[UploadFile, File(...)],
    category: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    """Bir dokümanı yükler, işler ve bilgi tabanına indeksler."""
    data = await file.read()
    doc = await service.ingest(
        filename=file.filename or "document", data=data, category=category
    )
    return DocumentResponse.from_domain(doc)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    repo: DocumentRepositoryDep, limit: int = 100, offset: int = 0
) -> DocumentListResponse:
    items = await repo.list(limit=limit, offset=offset)
    total = await repo.count()
    return DocumentListResponse(
        total=total, items=[DocumentResponse.from_domain(d) for d in items]
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, repo: DocumentRepositoryDep) -> DocumentResponse:
    doc = await repo.get(document_id)
    if doc is None:
        raise NotFoundError("Doküman bulunamadı.")
    return DocumentResponse.from_domain(doc)


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str, body: DocumentUpdate, repo: DocumentRepositoryDep
) -> DocumentResponse:
    """Dokümanı silmeden etkin/pasif yapar (pasifken retrieval'a dahil edilmez)."""
    doc = await repo.set_enabled(document_id, body.enabled)
    if doc is None:
        raise NotFoundError("Doküman bulunamadı.")
    return DocumentResponse.from_domain(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, service: IngestionServiceDep) -> None:
    deleted = await service.delete(document_id)
    if not deleted:
        raise NotFoundError("Doküman bulunamadı.")
