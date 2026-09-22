"""FastAPI uygulama fabrikası.

Uygulama tek bir `create_app()` fabrikasıyla kurulur; böylece testlerde ve
farklı ortamlarda temiz örnekler üretilebilir. Router'lar burada mount edilir.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routers import admin, chat, conversations, documents, health, projects
from app.config import get_settings
from app.database import init_models
from app.dependencies import get_vector_store
from app.exceptions import register_exception_handlers
from app.logging import configure_logging, get_logger
from app.observability import RequestContextMiddleware, metrics_endpoint
from app.security import require_api_key

logger = get_logger(__name__)


async def _run_startup_tasks() -> None:
    """DB tablolarını ve Qdrant collection'ını hazırlar (best-effort).

    Production'da şema Alembic ile yönetilir (`uv run alembic upgrade head`);
    burada geliştirmeyi kolaylaştırmak için idempotent kurulum yapılır.
    Sunuculara ulaşılamazsa uyarı loglanır, uygulama yine de ayağa kalkar.
    """
    try:
        await init_models()
        await get_vector_store().ensure_collection()
        logger.info("startup_tasks_ok")
    except Exception as exc:
        logger.warning("startup_tasks_skipped", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("app_startup", app=app.title, version=__version__)
    if settings.environment != "test":
        await _run_startup_tasks()
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    # Middleware (dıştan içe sıra: en son eklenen en dışta çalışır)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Prometheus scrape ucu (auth'suz, düz ASGI route)
    app.add_route("/metrics", metrics_endpoint, methods=["GET"])

    # Router'lar — health/metrics hariç tümü API anahtarıyla korunur.
    api_key_dep = [Depends(require_api_key)]
    app.include_router(health.router)
    app.include_router(documents.router, prefix=settings.api_prefix, dependencies=api_key_dep)
    app.include_router(chat.router, prefix=settings.api_prefix, dependencies=api_key_dep)
    app.include_router(conversations.router, prefix=settings.api_prefix, dependencies=api_key_dep)
    app.include_router(projects.router, prefix=settings.api_prefix, dependencies=api_key_dep)
    app.include_router(admin.router, prefix=settings.api_prefix, dependencies=api_key_dep)

    return app


app = create_app()
