"""Gözlemlenebilirlik: request-id, yapılandırılmış log ve Prometheus metrikleri.

Her isteğe bir `request_id` atanır, structlog contextvar'ına bağlanır, yanıt
başlığına eklenir ve HTTP metrikleri (sayım + latency) kaydedilir. Ayrıca alan
(domain) metrikleri — LLM token kullanımı, retrieval/chat latency, ingestion
sayaçları — servislerin çağırdığı hafif `record_*`/`observe_*` yardımcılarıyla
toplanır. Böylece Prometheus bağımlılığı bu tek modülde kalır (servisler
prometheus'u bilmez, sadece bu modüldeki fonksiyonları çağırır).

Metrikler MODÜL SEVİYESİNDE bir kez tanımlanır; birden çok `create_app()` örneği
(testler) çifte kayıt hatası vermez — /metrics global registry'yi okur.
"""

from __future__ import annotations

import time
from uuid import uuid4

import structlog
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging import get_logger
from app.models.domain import TokenUsage

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# --- Metrikler (modül seviyesinde tek sefer) -----------------------------------

HTTP_REQUESTS = Counter(
    "rag_http_requests_total",
    "Toplam HTTP isteği",
    ["method", "status"],
)
HTTP_LATENCY = Histogram(
    "rag_http_request_seconds",
    "HTTP istek süresi (saniye)",
    ["method"],
)
LLM_TOKENS = Counter(
    "rag_llm_tokens_total",
    "LLM token kullanımı",
    ["kind"],  # prompt | completion
)
RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_seconds",
    "Retrieval süresi (saniye)",
    ["mode"],  # dense | hybrid
)
CHAT_LATENCY = Histogram(
    "rag_chat_seconds",
    "Uçtan uca chat cevabı süresi (saniye)",
)
DOCS_INGESTED = Counter(
    "rag_documents_ingested_total",
    "Başarıyla indekslenen doküman sayısı",
)
CHUNKS_INDEXED = Counter(
    "rag_chunks_indexed_total",
    "İndekslenen toplam chunk sayısı",
)


# --- Servislerin çağırdığı hafif yardımcılar -----------------------------------


def record_llm_usage(usage: TokenUsage) -> None:
    if usage.prompt_tokens:
        LLM_TOKENS.labels("prompt").inc(usage.prompt_tokens)
    if usage.completion_tokens:
        LLM_TOKENS.labels("completion").inc(usage.completion_tokens)


def observe_retrieval(mode: str, seconds: float) -> None:
    RETRIEVAL_LATENCY.labels(mode).observe(seconds)


def observe_chat(seconds: float) -> None:
    CHAT_LATENCY.observe(seconds)


def record_ingestion(num_chunks: int) -> None:
    DOCS_INGESTED.inc()
    CHUNKS_INDEXED.inc(num_chunks)


def metrics_endpoint(_request: Request) -> Response:
    """Prometheus scrape ucu — global registry'yi tel formatında döner."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Model adına göre son gerçek çağrının başarılı olup olmadığı (Admin Dashboard'da
# yeşil/kırmızı durum noktası için). Ekstra API çağrısı yapıp kota harcamamak için
# proaktif health-check yerine gerçek kullanım sırasında pasif olarak güncellenir.
_MODEL_HEALTH: dict[str, bool] = {}


def record_model_health(model: str, ok: bool) -> None:
    _MODEL_HEALTH[model] = ok


def get_model_health(model: str) -> bool | None:
    """Son gözlemlenen durumu döner; hiç çağrılmadıysa `None` (bilinmiyor)."""
    return _MODEL_HEALTH.get(model)


def get_admin_metrics() -> dict:
    """Admin Dashboard için Prometheus registry'sinden hafif, JSON'a uygun özet.

    Ham `/metrics` tel formatını ayrıştırmak yerine (frontend'de gereksiz
    karmaşıklık), zaten toplanmış sayaç/histogram örneklerini burada okuyup
    düz sayılara indirger.
    """
    chat_sum = chat_count = 0.0
    for sample in CHAT_LATENCY.collect()[0].samples:
        if sample.name == "rag_chat_seconds_sum":
            chat_sum = sample.value
        elif sample.name == "rag_chat_seconds_count":
            chat_count = sample.value

    total_tokens = sum(
        s.value for s in LLM_TOKENS.collect()[0].samples if s.name == "rag_llm_tokens_total"
    )

    return {
        "chat_requests_total": int(chat_count),
        "avg_chat_latency_ms": round((chat_sum / chat_count) * 1000, 1) if chat_count else None,
        "total_llm_tokens": int(total_tokens),
    }


# --- Middleware ----------------------------------------------------------------


class RequestContextMiddleware(BaseHTTPMiddleware):
    """İstek başına request_id üretir, loglara bağlar, süreyi ölçer, HTTP metriği yazar.

    Latency ve sayaç yalnızca `method` ile etiketlenir (yol/path etiketi yok);
    böylece path parametreli uçlar kardinalite patlamasına yol açmaz. Uç-bazlı
    ölçüm için alan metrikleri (retrieval/chat histogramları) kullanılır.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            elapsed = time.perf_counter() - start
            HTTP_REQUESTS.labels(request.method, status).inc()
            HTTP_LATENCY.labels(request.method).observe(elapsed)
            logger.info(
                "request_completed",
                status=status,
                duration_ms=round(elapsed * 1000, 2),
            )

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
