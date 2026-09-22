"""API anahtarı doğrulama — health/metrics dışındaki tüm uçları korur.

`.env`'de `API_KEY` tanımlıysa istekler `X-API-Key` header'ı ile (tarayıcının
header ekleyemediği SSE/`EventSource` bağlantıları için `api_key` query param
ile) eşleşen anahtarı sağlamalıdır. Tanımlı değilse yalnızca development/test
rahatlığı için istekler serbest bırakılır ve bir kez uyarı loglanır.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.dependencies import SettingsDep
from app.logging import get_logger

logger = get_logger(__name__)
_warned = False


async def require_api_key(request: Request, settings: SettingsDep) -> None:
    if settings.environment == "test":
        return

    if not settings.api_key:
        global _warned
        if not _warned:
            logger.warning("api_key_not_configured_endpoints_unprotected")
            _warned = True
        return

    provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not provided or not secrets.compare_digest(provided, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya eksik API anahtarı",
        )
