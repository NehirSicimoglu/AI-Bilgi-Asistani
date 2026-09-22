"""Uygulama yapılandırması — .env üzerinden okunur (pydantic-settings).

Tüm ayarlar tek kaynaktan gelir; eksik/yanlış tipler uygulama başlarken
(fail-fast) hata verir. Sağlayıcıya özel anahtarlar başlangıçta opsiyoneldir,
ilgili özellik devreye girdiğinde `require_*` yardımcılarıyla zorunlu kılınır.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Uygulama ---
    app_name: str = "AI Knowledge Assistant"
    environment: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False  # production'da True → yapılandırılmış JSON log
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Güvenlik ---
    # `X-API-Key` header'ı ile korunan uçlar için paylaşılan anahtar. Boşsa
    # (yalnızca local development rahatlığı için) uçlar korumasız kalır ve bir
    # kez uyarı loglanır; production'a çıkmadan önce mutlaka ayarlanmalıdır.
    api_key: str | None = None

    # --- LLM (Gemini) ---
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    # NOT: gemini-2.5-flash yeni API anahtarlarına kapatıldı (2026-07); flash
    # ailesinin kararlı rolling alias'ı kullanılıyor. Model .env ile değiştirilebilir.
    llm_model: str = "gemini-flash-latest"
    # Sorgu yeniden yazma (query rewrite) kısa/basit bir yardımcı çağrıdır — ana
    # cevap kalitesini etkilemeden gecikmeyi azaltmak için daha hafif/hızlı bir
    # model kullanılır.
    llm_rewrite_model: str = "gemini-3.1-flash-lite"
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 2048

    # --- Embedding (Google) ---
    embedding_provider: str = "google"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # --- Sparse encoder (hybrid retrieval, BM25) ---
    sparse_encoder: str = "bm25"

    # --- Vector store (Qdrant) ---
    vector_store_provider: str = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "knowledge_base"

    # --- Veritabanı (PostgreSQL) ---
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"

    # --- Chunking / Retrieval ---
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 5
    retrieval_mode: Literal["dense", "hybrid"] = "hybrid"

    # --- Query Decomposition (çapraz-belge çoklu-sorgu getirme) ---
    # Cevabı birden çok belgeden bilgi birleştirmeyi gerektiren sorularda, tek
    # arama sorgusu ikincil belgeyi kaçırabilir. Açıkken soru önce alt-sorulara
    # bölünür, her biri ayrı getirilir ve sonuçlar birleştirilip tekilleştirilir.
    # Default KAPALI → mevcut davranış korunur; A/B ölçümü için açılır.
    enable_query_decomposition: bool = False
    # Bölmeden üretilecek en fazla alt-sorgu sayısı (üst sınır; model daha az da üretebilir).
    decomposition_max_subqueries: int = 3
    # Her alt-sorgu için çekilecek chunk sayısı (kör top_k artışının gürültüsü olmadan
    # hedefli getirme: ör. 3 alt-sorgu × 3 = ~9 aday, birleştirme sonrası tekilleşir).
    subquery_top_k: int = 3

    # --- Konuşma / bellek ---
    # Prompt ve query rewriting'e verilecek en son mesaj sayısı (çok turlu sohbet).
    chat_history_messages: int = 10

    # --- Dosya yükleme ---
    max_upload_mb: int = 25
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".docx", ".xlsx", ".txt", ".md"]
    )

    def require_gemini_api_key(self) -> str:
        if not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY tanımlı değil. .env dosyasına ekleyin."
            )
        return self.gemini_api_key


@lru_cache
def get_settings() -> Settings:
    """Tekil (singleton) ayar örneği — uygulama boyunca yeniden okunmaz."""
    return Settings()
