"""Proje API DTO'ları."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.domain import Project


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, p: Project) -> ProjectResponse:
        return cls(id=p.id, name=p.name, created_at=p.created_at)


class ProjectListResponse(BaseModel):
    total: int
    items: list[ProjectResponse]
