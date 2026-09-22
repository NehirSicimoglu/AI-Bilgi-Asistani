"""Sağlık kontrolü endpoint'leri."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Uygulamanın ayakta olduğunu bildirir (liveness)."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
    }
