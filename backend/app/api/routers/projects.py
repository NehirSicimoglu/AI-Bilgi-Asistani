"""Proje uçları: oluşturma, listeleme, yeniden adlandırma, silme.

Projeler sohbetleri gruplamak için kullanıcı tanımlı klasörlerdir; sohbetin
kendisi `/conversations/{id}` PATCH'i ile bir projeye taşınır.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.projects import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.dependencies import ProjectRepositoryDep
from app.exceptions import NotFoundError
from app.models.domain import Project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(req: ProjectCreate, repo: ProjectRepositoryDep) -> ProjectResponse:
    project = await repo.create(Project(name=req.name))
    return ProjectResponse.from_domain(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(repo: ProjectRepositoryDep) -> ProjectListResponse:
    items = await repo.list()
    total = await repo.count()
    return ProjectListResponse(total=total, items=[ProjectResponse.from_domain(p) for p in items])


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str, req: ProjectUpdate, repo: ProjectRepositoryDep
) -> ProjectResponse:
    project = await repo.rename(project_id, req.name)
    if project is None:
        raise NotFoundError("Proje bulunamadı.")
    return ProjectResponse.from_domain(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, repo: ProjectRepositoryDep) -> None:
    deleted = await repo.delete(project_id)
    if not deleted:
        raise NotFoundError("Proje bulunamadı.")
