"""Metadata filtre DTO'su — API'de yapılandırılmış filtreleme.

İstemci ham dict yerine tipli alanlarla filtreler; `to_filters()` bunu vector
store'un anladığı dict spesifikasyonuna çevirir (eşitlik / çoklu değer / aralık).
Her alan opsiyoneldir; verilenler AND'lenir.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MetadataFilter(BaseModel):
    document_id: str | list[str] | None = None
    document_name: str | list[str] | None = None
    category: str | list[str] | None = None
    # Doküman türü: ".pdf", ".docx", ".txt", ".md" (tek veya çoklu).
    extension: str | list[str] | None = Field(default=None)
    # Tarih aralığı (dahil): created_at epoch saniyesi üzerinden Range'e çevrilir.
    created_after: datetime | None = None
    created_before: datetime | None = None

    def to_filters(self) -> dict | None:
        """Vector store dict spesifikasyonuna çevirir; hiçbir alan yoksa None."""
        spec: dict = {}
        if self.document_id is not None:
            spec["document_id"] = self.document_id
        if self.document_name is not None:
            spec["document_name"] = self.document_name
        if self.category is not None:
            spec["category"] = self.category
        if self.extension is not None:
            spec["extension"] = self.extension

        date_range: dict = {}
        if self.created_after is not None:
            date_range["gte"] = self.created_after.timestamp()
        if self.created_before is not None:
            date_range["lte"] = self.created_before.timestamp()
        if date_range:
            spec["created_at"] = date_range

        return spec or None
