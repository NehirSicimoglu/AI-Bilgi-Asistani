"""Async veritabanı motoru ve oturum yönetimi.

Motor tembel (lazy) kurulur — import anında bağlantı açılmaz; ilk sorguda açılır.
Böylece uygulama, Postgres ayakta olmadan da import edilebilir (birim testleri).
Şemanın kaynağı Alembic migration'larıdır; `init_models()` yalnızca geliştirmede
tabloları hızlıca kurmak içindir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.models.db import Base


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI bağımlılığı: istek başına bir oturum açar/kapatır."""
    async with get_sessionmaker()() as session:
        yield session


async def init_models() -> None:
    """Tabloları oluşturur — yalnızca geliştirme kolaylığı için.

    Şema değişikliklerinin kaynağı `alembic/versions/` altındaki migration'lardır
    (`uv run alembic upgrade head`). Bu fonksiyon var olan tablolara sütun
    EKLEMEZ; şeması eskimiş bir veritabanını yalnızca migration günceller.
    """
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
