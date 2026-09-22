"""Doküman repository — DocumentRow (DB) ile Document (domain) arasında köprü."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import DocumentRow
from app.models.domain import Document, DocumentStatus


def _to_domain(row: DocumentRow) -> Document:
    return Document(
        id=row.id,
        filename=row.filename,
        extension=row.extension,
        category=row.category,
        size_bytes=row.size_bytes,
        num_chunks=row.num_chunks,
        status=DocumentStatus(row.status),
        error=row.error,
        enabled=row.enabled,
        metadata=row.doc_metadata or {},
        created_at=row.created_at,
    )


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, doc: Document) -> Document:
        row = DocumentRow(
            id=doc.id,
            filename=doc.filename,
            extension=doc.extension,
            category=doc.category,
            size_bytes=doc.size_bytes,
            num_chunks=doc.num_chunks,
            status=str(doc.status),
            error=doc.error,
            enabled=doc.enabled,
            doc_metadata=doc.metadata,
            created_at=doc.created_at,
        )
        self._session.add(row)
        await self._session.commit()
        return doc

    async def update(self, doc: Document) -> None:
        row = await self._session.get(DocumentRow, doc.id)
        if row is None:
            return
        row.status = str(doc.status)
        row.num_chunks = doc.num_chunks
        row.error = doc.error
        row.doc_metadata = doc.metadata
        await self._session.commit()

    async def get(self, document_id: str) -> Document | None:
        row = await self._session.get(DocumentRow, document_id)
        return _to_domain(row) if row else None

    async def set_enabled(self, document_id: str, enabled: bool) -> Document | None:
        """Dokümanı retrieval'dan hariç tutmadan (silmeden) etkin/pasif yapar."""
        row = await self._session.get(DocumentRow, document_id)
        if row is None:
            return None
        row.enabled = enabled
        await self._session.commit()
        return _to_domain(row)

    async def list_disabled_ids(self) -> set[str]:
        stmt = select(DocumentRow.id).where(DocumentRow.enabled.is_(False))
        rows = (await self._session.scalars(stmt)).all()
        return set(rows)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Document]:
        stmt = (
            select(DocumentRow)
            .order_by(DocumentRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [_to_domain(r) for r in rows]

    async def delete(self, document_id: str) -> bool:
        row = await self._session.get(DocumentRow, document_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True

    async def count(self) -> int:
        return (await self._session.scalar(select(func.count(DocumentRow.id)))) or 0

    async def count_by_status(self) -> dict[str, int]:
        """Admin Dashboard'daki indeks durumu özeti için (status -> sayı)."""
        stmt = select(DocumentRow.status, func.count(DocumentRow.id)).group_by(
            DocumentRow.status
        )
        rows = (await self._session.execute(stmt)).all()
        return {status: count for status, count in rows}
