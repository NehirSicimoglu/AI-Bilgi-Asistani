"""Google (Gemini) embedding sağlayıcısı — `EmbeddingProvider` implementasyonu.

`google-genai` async istemcisi ile metinleri vektöre çevirir. task_type ayrımı
retrieval kalitesini artırır: dokümanlar RETRIEVAL_DOCUMENT, sorgular
RETRIEVAL_QUERY olarak gömülür. Geçici hatalarda tenacity ile yeniden dener.

İstemci dışarıdan enjekte edilebilir (test için); verilmezse api_key'den kurulur.
"""

from __future__ import annotations

import re

from google import genai
from google.genai import types
from tenacity import RetryCallState, retry, stop_after_attempt

from app.config import Settings
from app.exceptions import ProviderError
from app.logging import get_logger

logger = get_logger(__name__)

_BATCH_SIZE = 100
_MAX_ATTEMPTS = 5
# Google 429 yanıtındaki "retryDelay: '55s'" alanını yakalar.
_RETRY_DELAY_RE = re.compile(r"retryDelay'?\"?\s*[:=]\s*'?\"?(\d+(?:\.\d+)?)s")
_RATE_LIMIT_FALLBACK_WAIT_S = 30.0
_RATE_LIMIT_MAX_WAIT_S = 90.0
_TRANSIENT_MAX_WAIT_S = 8.0


def _retry_wait(retry_state: RetryCallState) -> float:
    """429'da sağlayıcının bildirdiği süre kadar, diğer hatalarda kısa exponential bekler."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    delay = getattr(exc, "retry_delay_s", None)
    if delay is not None:
        return min(delay + 1.0, _RATE_LIMIT_MAX_WAIT_S)
    return min(_TRANSIENT_MAX_WAIT_S, 0.5 * (2 ** (retry_state.attempt_number - 1)))


class GoogleEmbeddingProvider:
    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self._model = settings.embedding_model
        self._dim = settings.embedding_dim
        self._client = client or genai.Client(api_key=settings.require_gemini_api_key())

    @property
    def dim(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            vectors.extend(await self._embed(batch, task_type="RETRIEVAL_DOCUMENT"))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        result = await self._embed([text], task_type="RETRIEVAL_QUERY")
        return result[0]

    @retry(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=_retry_wait,
        reraise=True,
    )
    async def _embed(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        try:
            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self._dim,
                ),
            )
        except Exception as exc:
            error = ProviderError(f"Embedding üretilemedi: {exc}")
            # 429 (kota) hatasında sağlayıcının önerdiği bekleme süresini taşı;
            # _retry_wait bu değeri okuyarak bir sonraki denemeyi zamanlar.
            if getattr(exc, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(exc):
                match = _RETRY_DELAY_RE.search(str(exc))
                error.retry_delay_s = (
                    float(match.group(1)) if match else _RATE_LIMIT_FALLBACK_WAIT_S
                )
                logger.warning(
                    "embedding_rate_limited",
                    retry_in_s=error.retry_delay_s,
                    count=len(texts),
                )
            else:
                logger.error("embedding_failed", error=str(exc), count=len(texts))
            raise error from exc

        return [list(e.values) for e in response.embeddings]
