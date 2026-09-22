"""LLM sağlayıcı interface'i (port).

Servisler bu Protocol'e bağlanır; somut sağlayıcı (Gemini, ileride başka bir
bulut sağlayıcısı veya yerel model) `dependencies.py` üzerinden seçilir. Yeni
sağlayıcı eklemek = bu Protocol'ü implemente eden tek bir sınıf yazmak.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.models.domain import Role, TokenUsage


class LLMMessage(BaseModel):
    role: Role
    content: str


class LLMResponse(BaseModel):
    text: str
    usage: TokenUsage = TokenUsage()


@runtime_checkable
class LLMProvider(Protocol):
    """Metin üretimi — hem tek seferlik hem streaming."""

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Tam cevabı tek seferde üretir.

        `model` verilirse sağlayıcının varsayılan modelini geçici olarak değiştirir.
        """
        ...

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Cevabı parça parça (token) üretir — SSE için."""
        ...
