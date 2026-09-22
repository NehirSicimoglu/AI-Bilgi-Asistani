"""Proje repository — ProjectRow (DB) ile Project (domain) arasında köprü.

Projeler, sohbetleri gruplamak için kullanıcı tanımlı klasörlerdir. Bir proje
silindiğinde içindeki sohbetler silinmez; yalnızca `project_id` NULL'a döner
(bkz. `ConversationRow.project_id` ON DELETE SET NULL).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ProjectRow
from app.models.domain import Project


def _to_domain(row: ProjectRow) -> Project:
    return Project(id=row.id, name=row.name, created_at=row.created_at)


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, project: Project) -> Project:
        row = ProjectRow(id=project.id, name=project.name, created_at=project.created_at)
        self._session.add(row)
        await self._session.commit()
        return project

    async def list(self) -> list[Project]:
        stmt = select(ProjectRow).order_by(ProjectRow.created_at.asc())
        rows = (await self._session.scalars(stmt)).all()
        return [_to_domain(r) for r in rows]

    async def count(self) -> int:
        return (await self._session.scalar(select(func.count(ProjectRow.id)))) or 0

    async def rename(self, project_id: str, name: str) -> Project | None:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            return None
        row.name = name
        await self._session.commit()
        await self._session.refresh(row)
        return _to_domain(row)

    async def delete(self, project_id: str) -> bool:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True
