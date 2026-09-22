"""evaluation/report.py testleri (saf formatlama, ağsız)."""

from __future__ import annotations

from evaluation.metrics import QuestionResult
from evaluation.report import render_report


def _result(id: str, *, correct: bool, hit: bool) -> QuestionResult:
    return QuestionResult(
        id=id,
        question="Qdrant nedir?",
        answer="Qdrant bir vektör veritabanıdır [1].",
        expected_source="qdrant-overview.md",
        retrieved_sources=["qdrant-overview.md" if hit else "baska.md"],
        cited_sources=["qdrant-overview.md"],
        latency_ms=42.0,
        coverage=1.0 if correct else 0.2,
        is_correct=correct,
        is_source_hit=hit,
        rr=1.0 if hit else 0.0,
        is_citation_correct=hit,
    )


def test_render_report_all_correct_has_no_failures_section_entries() -> None:
    results = [_result("q1", correct=True, hit=True)]
    from evaluation.metrics import EvalSummary

    summary = EvalSummary.from_results(results)
    report = render_report(summary, results)
    assert "Toplam soru: **1**" in report
    assert "Başarısız örnek yok" in report


def test_render_report_lists_failed_examples_with_reason() -> None:
    results = [_result("q1", correct=True, hit=True), _result("q2", correct=False, hit=False)]
    from evaluation.metrics import EvalSummary

    summary = EvalSummary.from_results(results)
    report = render_report(summary, results)
    assert "Başarısız Örnekler (1)" in report
    assert "q2" in report
    assert "kaynak ıskası" in report
    assert "düşük kapsama" in report
