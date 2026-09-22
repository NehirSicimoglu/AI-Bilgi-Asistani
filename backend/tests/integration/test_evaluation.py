"""Değerlendirme altyapısı: metrikler, judge, runner (ağsız, fake'lerle)."""

from __future__ import annotations

from app.ingestion.sparse import Bm25SparseEncoder
from app.models.domain import TokenUsage
from app.providers.llm.base import LLMResponse
from app.repositories.document_repo import DocumentRepository
from app.services.chat import ChatService
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService
from evaluation.judge import LLMJudge, _parse_score
from evaluation.metrics import (
    EvalSummary,
    QuestionResult,
    keyword_coverage,
    reciprocal_rank,
    source_hit,
)
from evaluation.runner import GoldenItem, run_evaluation
from tests.conftest import FakeLLM

# --- Deterministik metrikler ---------------------------------------------------


def test_keyword_coverage() -> None:
    assert keyword_coverage("Qdrant bir vektör veritabanıdır", ["Qdrant", "vektör"]) == 1.0
    assert keyword_coverage("sadece biri", ["biri", "yok"]) == 0.5
    assert keyword_coverage("herhangi", []) == 1.0


def test_reciprocal_rank_and_source_hit() -> None:
    srcs = ["a.md", "b.md", "c.md"]
    assert reciprocal_rank(srcs, "a.md") == 1.0
    assert reciprocal_rank(srcs, "b.md") == 0.5
    assert reciprocal_rank(srcs, "yok.md") == 0.0
    assert source_hit(srcs, "c.md") is True
    assert source_hit(srcs, "yok.md") is False


def test_summary_aggregation() -> None:
    def qr(correct: bool, hit: bool, rr: float) -> QuestionResult:
        return QuestionResult(
            id="x", question="q", answer="a", expected_source="s.md",
            retrieved_sources=[], cited_sources=[], latency_ms=10.0,
            coverage=1.0 if correct else 0.0, is_correct=correct,
            is_source_hit=hit, rr=rr, is_citation_correct=hit,
        )

    results = [qr(True, True, 1.0), qr(False, True, 0.5), qr(True, False, 0.0)]
    s = EvalSummary.from_results(results)
    assert s.total == 3
    assert s.correct == 2
    assert s.source_hits == 2
    assert abs(s.mrr - 0.5) < 1e-9
    assert set(s.failures) == {"x"}  # hepsi aynı id; en az bir başarısız var
    assert s.avg_faithfulness is None  # yargıç çalışmadı


# --- LLM judge -----------------------------------------------------------------


def test_parse_score() -> None:
    assert _parse_score("0.8") == 0.8
    assert _parse_score("Puan: 0,75 çünkü...") == 0.75
    assert _parse_score("1") == 1.0
    assert _parse_score("1.0 puan veriyorum") == 1.0
    assert _parse_score("5") is None  # 0-1 kontratı dışı → geçersiz
    assert _parse_score("cevap yok") is None


async def test_llm_judge_scores() -> None:
    class ScoringLLM:
        async def generate(
            self, messages, *, system=None, temperature=None, max_tokens=None, model=None
        ):
            return LLMResponse(text="0.9", usage=TokenUsage())

        async def stream(self, messages, *, system=None, temperature=None, max_tokens=None):
            yield "0.9"

    judge = LLMJudge(ScoringLLM())
    assert await judge.faithfulness("cevap", ["bağlam"]) == 0.9
    assert await judge.answer_relevancy("soru", "cevap") == 0.9


# --- Runner (uçtan uca, fake'lerle) --------------------------------------------


async def test_run_evaluation_end_to_end(
    test_settings, fake_embedding, vector_store, sessionmaker
) -> None:
    repo = DocumentRepository(sessionmaker())
    ing = IngestionService(
        test_settings, fake_embedding, vector_store, repo, Bm25SparseEncoder()
    )
    await ing.ingest(
        filename="qdrant-overview.md",
        data=b"Qdrant bir vektor veritabanidir ve benzerlik aramasi yapar. " * 15,
        category="databases",
    )

    retrieval = RetrievalService(
        test_settings, fake_embedding, vector_store, Bm25SparseEncoder()
    )
    chat = ChatService(test_settings, retrieval, FakeLLM("Qdrant bir vektor veritabanidir [1]."))

    golden = [
        GoldenItem(
            id="q1",
            question="Qdrant nedir?",
            expected_source="qdrant-overview.md",
            expected_keywords=["Qdrant", "vektor"],
        )
    ]
    results, summary = await run_evaluation(golden, retrieval, chat, top_k=5)

    assert summary.total == 1
    r = results[0]
    assert r.is_source_hit is True          # BM25 doğru dokümanı getirdi
    assert r.is_correct is True             # cevap anahtar kelimeleri içeriyor
    assert r.is_citation_correct is True    # citation beklenen kaynağa işaret ediyor
    assert r.latency_ms >= 0
    assert summary.avg_faithfulness is None  # judge verilmedi
