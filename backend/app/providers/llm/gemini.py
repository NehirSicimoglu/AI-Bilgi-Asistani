"""Google Gemini LLM sağlayıcısı — `LLMProvider` implementasyonu.

`generate()` tam cevabı, `stream()` cevabı parça parça (SSE için) üretir.
Model adı `.env`'deki `LLM_MODEL`'den gelir (varsayılan `gemini-flash-latest`);
kod hiçbir modele gömülü değildir. İstemci test için enjekte edilebilir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import Settings
from app.exceptions import ProviderError
from app.logging import get_logger
from app.models.domain import Role, TokenUsage
from app.observability import record_model_health
from app.providers.llm.base import LLMMessage, LLMResponse

logger = get_logger(__name__)

# Gemini rolleri: kullanıcı "user", asistan "model"
_ROLE_MAP = {Role.USER: "user", Role.ASSISTANT: "model"}


class GeminiLLMProvider:
    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_output_tokens
        self._client = client or genai.Client(api_key=settings.require_gemini_api_key())

    def _contents(self, messages: list[LLMMessage]) -> list[types.Content]:
        return [
            types.Content(role=_ROLE_MAP[m.role], parts=[types.Part(text=m.content)])
            for m in messages
        ]

    def _config(
        self, system: str | None, temperature: float | None, max_tokens: int | None
    ) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature if temperature is None else temperature,
            max_output_tokens=max_tokens or self._max_tokens,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=8),
        reraise=True,
    )
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        used_model = model or self._model
        try:
            response = await self._client.aio.models.generate_content(
                model=used_model,
                contents=self._contents(messages),
                config=self._config(system, temperature, max_tokens),
            )
        except Exception as exc:
            logger.error("llm_generate_failed", error=str(exc))
            record_model_health(used_model, False)
            raise ProviderError(f"LLM cevabı üretilemedi: {exc}") from exc
        record_model_health(used_model, True)
        return LLMResponse(text=response.text or "", usage=_usage(response))

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=self._contents(messages),
                config=self._config(system, temperature, max_tokens),
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
            record_model_health(self._model, True)
        except Exception as exc:
            logger.error("llm_stream_failed", error=str(exc))
            record_model_health(self._model, False)
            raise ProviderError(f"LLM stream başarısız: {exc}") from exc


def _usage(response) -> TokenUsage:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=meta.prompt_token_count or 0,
        completion_tokens=meta.candidates_token_count or 0,
        total_tokens=meta.total_token_count or 0,
    )
