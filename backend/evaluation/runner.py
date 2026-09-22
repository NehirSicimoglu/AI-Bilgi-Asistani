"""Değerlendirme koşucusu — golden set'i sistemde çalıştırır.

`run_evaluation` saf bir async fonksiyondur (servisler enjekte edilir) → ağsız
fake'lerle testlenebilir. `main` gerçek bağımlılıkları (Qdrant/Postgres/Gemini)
DI fabrikalarıyla kurar ve raporu yazar.

Çalıştırma:
    uv run python -m evaluation.runner                 # deterministik metrikler
    uv run python -m evaluation.runner --judge         # + Gemini LLM yargısı
    uv run python -m evaluation.runner --limit 10 --out eval_report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.logging import get_logger
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService
from evaluation.judge import LLMJudge
from evaluation.metrics import EvalSummary, QuestionResult

logger = get_logger("eval_runner")

_DEFAULT_GOLDEN = Path(__file__).resolve().parent / "golden_set.jsonl"


@dataclass
class GoldenItem:
    id: str
    question: str
    expected_source: str
    expected_keywords: list[str]
    ground_truth: str = ""
    category: str = ""


def load_golden(path: Path) -> list[GoldenItem]:
    items: list[GoldenItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        items.append(
            GoldenItem(
                id=o["id"],
                question=o["question"],
                expected_source=o["expected_source"],
                expected_keywords=o.get("expected_keywords", []),
                ground_truth=o.get("ground_truth", ""),
                category=o.get("category", ""),
            )
        )
    return items


async def run_evaluation(
    golden: list[GoldenItem],
    retrieval: RetrievalService,
    chat: ChatService,
    *,
    top_k: int = 5,
    judge: LLMJudge | None = None,
) -> tuple[list[QuestionResult], EvalSummary]:
    results: list[QuestionResult] = []
    for item in golden:
        # Retrieval kalitesi (source hit / bağlam) için ayrı çağrı.
        retrieved = await retrieval.retrieve(item.question, top_k=top_k)
        retrieved_sources = [r.document_name for r in retrieved]
        contexts = [r.text for r in retrieved]

        # Kullanıcı deneyimi: chat cevabı + citation + latency.
        start = time.perf_counter()
        chat_result = await chat.answer(item.question, top_k=top_k)
        latency_ms = (time.perf_counter() - start) * 1000

        result = QuestionResult.build(
            id=item.id,
            question=item.question,
            answer=chat_result.answer,
            expected_source=item.expected_source,
            expected_keywords=item.expected_keywords,
            retrieved_sources=retrieved_sources,
            cited_sources=[c.document_name for c in chat_result.citations],
            latency_ms=latency_ms,
            ground_truth=item.ground_truth,
        )

        if judge is not None:
            result.faithfulness = await judge.faithfulness(chat_result.answer, contexts)
            result.answer_relevancy = await judge.answer_relevancy(
                item.question, chat_result.answer
            )

        results.append(result)

    return results, EvalSummary.from_results(results)


async def _main_async(args: argparse.Namespace) -> None:
    from app.config import get_settings
    from app.dependencies import (
        get_embedding_provider,
        get_llm_provider,
        get_sparse_encoder,
        get_vector_store,
    )
    from app.logging import configure_logging
    from evaluation.report import render_report, write_report

    settings = get_settings()
    configure_logging(settings)

    embedding = get_embedding_provider()
    vector_store = get_vector_store()
    sparse = get_sparse_encoder()
    llm = get_llm_provider()
    retrieval = RetrievalService(settings, embedding, vector_store, sparse)
    chat = ChatService(settings, retrieval, llm)
    judge = LLMJudge(llm) if args.judge else None

    golden = load_golden(Path(args.golden))
    if args.limit:
        golden = golden[: args.limit]

    print(f"Değerlendirme başlıyor: {len(golden)} soru, judge={'açık' if judge else 'kapalı'}")
    results, summary = await run_evaluation(
        golden, retrieval, chat, top_k=args.top_k, judge=judge
    )

    report = render_report(summary, results)
    print("\n" + report)
    if args.out:
        write_report(Path(args.out), report)
        print(f"\nRapor yazıldı: {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG golden set değerlendirmesi.")
    parser.add_argument("--golden", default=str(_DEFAULT_GOLDEN), help="Golden set (jsonl)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0, help="İlk N soru (0=hepsi)")
    parser.add_argument("--judge", action="store_true", help="Gemini LLM yargısını aç")
    parser.add_argument("--out", default="", help="Markdown rapor çıktısı yolu")
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
