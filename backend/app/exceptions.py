"""Uygulama exception hiyerarşisi ve FastAPI handler'ları.

Servisler bu domain exception'larını fırlatır; API katmanı bunları uygun HTTP
durum kodlarına çevirir. Böylece iş mantığı HTTP'den habersiz kalır (SRP).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Tüm uygulama hatalarının kökü."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class UnsupportedFileTypeError(ValidationError):
    code = "unsupported_file_type"


class CorruptFileError(ValidationError):
    """Uzantısı desteklenen ama içeriği okunamayan dosya (bozuk/yarım inmiş)."""

    code = "corrupt_file"


class ProviderError(AppError):
    """LLM/Embedding/VectorStore gibi dış sağlayıcı hatası."""

    status_code = 502
    code = "provider_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error",
            code=exc.code,
            status=exc.status_code,
            path=request.url.path,
            message=exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Beklenmeyen bir hata oluştu.",
                }
            },
        )
