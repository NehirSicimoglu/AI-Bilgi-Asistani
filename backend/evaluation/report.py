"""Değerlendirme raporu — özet metrikler + başarısız örnek analizi.

Rapor şu çıktıları içerir: başarılı cevap sayısı, kaynak gösterme doğruluğu,
ortalama latency ve başarısız örneklerin analizi. RAGAS-benzeri LLM metrikleri
(faithfulness, answer relevancy) yargıç açıksa eklenir.
"""

from __future__ import annotations

from pathlib import Path

from evaluation.metrics import EvalSummary, QuestionResult


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_report(summary: EvalSummary, results: list[QuestionResult]) -> str:
    lines: list[str] = []
    lines.append("# RAG Değerlendirme Raporu")
    lines.append("")
    lines.append("## Özet")
    lines.append("")
    lines.append(f"- Toplam soru: **{summary.total}**")
    lines.append(
        f"- Doğru cevap: **{summary.correct}/{summary.total}** ({_pct(summary.accuracy)})"
    )
    lines.append(
        f"- Kaynak isabeti (retrieval): **{summary.source_hits}/{summary.total}** "
        f"({_pct(summary.source_hit_rate)})"
    )
    lines.append(f"- MRR (sıralama kalitesi): **{summary.mrr:.3f}**")
    lines.append(
        f"- Citation doğruluğu: **{summary.citation_correct}/{summary.total}** "
        f"({_pct(summary.citation_accuracy)})"
    )
    lines.append("")
    lines.append("### Üretim (cevap) metrikleri — referans cevaba göre, LLM'siz")
    lines.append("")
    lines.append(f"- Exact Match (EM): **{_pct(summary.exact_match)}**")
    lines.append(f"- Token-F1 (kelime örtüşmesi): **{summary.token_f1:.3f}**")
    lines.append(f"- ROUGE-L (LCS tabanlı F1): **{summary.rouge_l:.3f}**")
    lines.append("")
    lines.append(f"- Ortalama latency: **{summary.avg_latency_ms:.1f} ms**")
    lines.append(f"- p95 latency: **{summary.p95_latency_ms:.1f} ms**")
    if summary.avg_faithfulness is not None:
        lines.append(f"- Faithfulness (LLM yargısı): **{summary.avg_faithfulness:.3f}**")
    if summary.avg_answer_relevancy is not None:
        lines.append(
            f"- Answer relevancy (LLM yargısı): **{summary.avg_answer_relevancy:.3f}**"
        )
    lines.append("")

    # Başarısız örnek analizi
    failed = [r for r in results if r.id in set(summary.failures)]
    lines.append(f"## Başarısız Örnekler ({len(failed)})")
    lines.append("")
    if not failed:
        lines.append("Başarısız örnek yok. 🎉")
    else:
        lines.append("| id | soru | beklenen kaynak | getirilen (ilk 3) | kapsama | neden |")
        lines.append("|---|---|---|---|---|---|")
        for r in failed:
            reasons = []
            if not r.is_correct:
                reasons.append("düşük kapsama")
            if not r.is_source_hit:
                reasons.append("kaynak ıskası")
            top3 = ", ".join(r.retrieved_sources[:3]) or "—"
            q = r.question if len(r.question) <= 50 else r.question[:47] + "..."
            lines.append(
                f"| {r.id} | {q} | {r.expected_source} | {top3} | "
                f"{_pct(r.coverage)} | {', '.join(reasons)} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, report: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
