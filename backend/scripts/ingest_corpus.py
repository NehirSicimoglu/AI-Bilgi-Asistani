"""Bir klasördeki dokümanları toplu indeksler — data/corpus/ → Qdrant + Postgres.

PDF/DOCX/XLSX/TXT/MD karışık bir klasörü, alt klasör adlarını `category` olarak
kullanarak gerçek ingestion pipeline'ından (parse → chunk → embed → index)
geçirir. Tek tek yükleme için frontend'deki `POST /documents` ucu da kullanılabilir;
bu betik toplu yükleme içindir.

Gerçek bağımlılıklar gerekir: Qdrant, PostgreSQL ve Gemini embedding anahtarı
(backend/.env).

Çalıştırma:
    uv run python -m scripts.ingest_corpus --corpus <klasör>
    uv run python -m scripts.ingest_corpus --corpus <klasör> --reset  # önce sıfırla
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.config import get_settings
from app.database import get_sessionmaker, init_models
from app.dependencies import (
    get_embedding_provider,
    get_sparse_encoder,
    get_vector_store,
)
from app.logging import configure_logging, get_logger
from app.repositories.document_repo import DocumentRepository
from app.services.ingestion import IngestionService

logger = get_logger("ingest_corpus")

_DEFAULT_CORPUS = Path(__file__).resolve().parent.parent / "data" / "corpus"


async def ingest_corpus(corpus_dir: Path, *, reset: bool) -> None:
    settings = get_settings()
    configure_logging(settings)

    embedding = get_embedding_provider()
    vector_store = get_vector_store()
    sparse = get_sparse_encoder()

    await init_models()
    if reset:
        await vector_store.reset_collection()
    else:
        await vector_store.ensure_collection()

    files = sorted(p for p in corpus_dir.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"Korpus boş veya bulunamadı: {corpus_dir}")

    maker = get_sessionmaker()
    indexed = 0
    failed = 0
    async with maker() as session:
        service = IngestionService(
            settings, embedding, vector_store, DocumentRepository(session), sparse
        )
        for i, path in enumerate(files, 1):
            category = path.parent.name
            try:
                doc = await service.ingest(
                    filename=path.name, data=path.read_bytes(), category=category
                )
                indexed += 1
                print(f"[{i}/{len(files)}] ✓ {category}/{path.name} ({doc.num_chunks} chunk)")
            except Exception as exc:
                failed += 1
                print(f"[{i}/{len(files)}] ✗ {category}/{path.name} — {exc}")

    total_chunks = await vector_store.count()
    print(
        f"\nBitti. İndekslenen doküman: {indexed}, başarısız: {failed}, "
        f"toplam chunk (Qdrant): {total_chunks}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Korpusu bilgi tabanına indeksler.")
    parser.add_argument("--corpus", default=str(_DEFAULT_CORPUS), help="Korpus dizini")
    parser.add_argument(
        "--reset", action="store_true", help="İndekslemeden önce koleksiyonu sıfırla"
    )
    args = parser.parse_args()
    asyncio.run(ingest_corpus(Path(args.corpus), reset=args.reset))


if __name__ == "__main__":
    main()
