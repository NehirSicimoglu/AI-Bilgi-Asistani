"""Değerlendirme metrikleri — deterministik, LLM'siz, ağsız.

Bu metrikler golden set'teki `expected_source` / `expected_keywords` üzerinden
hesaplanır; LLM yargısı gerektirmez, bu yüzden tekrarlanabilir ve testlenebilir.
LLM-yargılı metrikler (faithfulness, answer relevancy) ayrı modüldedir (judge.py).

Ölçülenler:
- **source_hit** (context recall vekili): beklenen kaynak getirilen kaynaklar arasında mı.
- **reciprocal_rank**: beklenen kaynağın getirilenlerdeki sırasının tersi (sıralama kalitesi).
- **citation_correct**: cevap beklenen kaynağa atıf yapmış mı.
- **keyword_coverage / answer_correct**: beklenen anahtar kelimelerin cevaptaki oranı.
- **latency**: uçtan uca süre (runner ölçer).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# --- Referans-tabanlı üretim metrikleri (deterministik, LLM'siz) --------------
#
# ground_truth (referans cevap) ile sistem cevabını kelime düzeyinde karşılaştırır.
# Bunlar QA/RAG literatüründe standart, tekrarlanabilir ve LLM yargısı gerektirmez:
# - exact_match: normalize edilmiş metinler birebir aynı mı (katı üst sınır).
# - token_f1: SQuAD tarzı kelime örtüşmesi F1'i (precision/recall harmonik ort.).
# - rouge_l: en uzun ortak alt dizi (LCS) tabanlı F1 — kelime sırasını da ödüllendirir.

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    """Metni küçük harfe indirip noktalama atarak kelime listesine böler (Türkçe uyumlu)."""
    return _TOKEN_RE.findall(text.casefold())


def exact_match(prediction: str, ground_truth: str) -> bool:
    """Normalize edilmiş (küçük harf + noktalamasız) metinler birebir aynı mı."""
    return _tokens(prediction) == _tokens(ground_truth)


def token_f1(prediction: str, ground_truth: str) -> float:
    """SQuAD tarzı kelime düzeyi F1 (0..1). Serbest metin cevapları için EM'den adildir."""
    pred, truth = _tokens(prediction), _tokens(ground_truth)
    if not pred and not truth:
        return 1.0
    if not pred or not truth:
        return 0.0
    overlap = sum((Counter(pred) & Counter(truth)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(truth)
    return 2 * precision * recall / (precision + recall)


def _lcs_length(a: list[str], b: list[str]) -> int:
    """İki kelime dizisinin en uzun ortak alt dizisi (LCS) uzunluğu."""
    prev = [0] * (len(b) + 1)
    for x in a:
        curr = [0] * (len(b) + 1)
        for j, y in enumerate(b, start=1):
            curr[j] = prev[j - 1] + 1 if x == y else max(prev[j], curr[j - 1])
        prev = curr
    return prev[-1]


def rouge_l(prediction: str, ground_truth: str) -> float:
    """ROUGE-L: LCS tabanlı F1 (0..1). Özet/uzun cevap kalitesinde yaygın kullanılır."""
    pred, truth = _tokens(prediction), _tokens(ground_truth)
    if not pred or not truth:
        return 0.0
    lcs = _lcs_length(pred, truth)
    if lcs == 0:
        return 0.0
    precision = lcs / len(pred)
    recall = lcs / len(truth)
    return 2 * precision * recall / (precision + recall)


def keyword_coverage(answer: str, keywords: list[str]) -> float:
    """Beklenen anahtar kelimelerin cevapta bulunma oranı (0..1), büyük/küçük harf duyarsız."""
    if not keywords:
        return 1.0
    text = answer.casefold()
    hits = sum(1 for k in keywords if k.casefold() in text)
    return hits / len(keywords)


def answer_correct(answer: str, keywords: list[str], *, threshold: float = 0.5) -> bool:
    """Anahtar kelime kapsaması eşiği geçiyorsa cevap 'doğru' sayılır."""
    return keyword_coverage(answer, keywords) >= threshold


def source_hit(retrieved_sources: list[str], expected_source: str) -> bool:
    return expected_source in retrieved_sources


def reciprocal_rank(retrieved_sources: list[str], expected_source: str) -> float:
    """Beklenen kaynağın sırasının tersi (1. sırada=1.0, yoksa 0.0)."""
    for i, src in enumerate(retrieved_sources, start=1):
        if src == expected_source:
            return 1.0 / i
    return 0.0


def citation_correct(cited_sources: list[str], expected_source: str) -> bool:
    return expected_source in cited_sources


@dataclass
class QuestionResult:
    id: str
    question: str
    answer: str
    expected_source: str
    retrieved_sources: list[str]
    cited_sources: list[str]
    latency_ms: float
    coverage: float
    is_correct: bool
    is_source_hit: bool
    rr: float
    is_citation_correct: bool
    em: float = 0.0
    f1: float = 0.0
    rouge: float = 0.0
    faithfulness: float | None = None
    answer_relevancy: float | None = None

    @classmethod
    def build(
        cls,
        *,
        id: str,
        question: str,
        answer: str,
        expected_source: str,
        expected_keywords: list[str],
        retrieved_sources: list[str],
        cited_sources: list[str],
        latency_ms: float,
        ground_truth: str = "",
    ) -> QuestionResult:
        cov = keyword_coverage(answer, expected_keywords)
        return cls(
            id=id,
            question=question,
            answer=answer,
            expected_source=expected_source,
            retrieved_sources=retrieved_sources,
            cited_sources=cited_sources,
            latency_ms=latency_ms,
            coverage=cov,
            is_correct=cov >= 0.5,
            is_source_hit=source_hit(retrieved_sources, expected_source),
            rr=reciprocal_rank(retrieved_sources, expected_source),
            is_citation_correct=citation_correct(cited_sources, expected_source),
            em=float(exact_match(answer, ground_truth)) if ground_truth else 0.0,
            f1=token_f1(answer, ground_truth) if ground_truth else 0.0,
            rouge=rouge_l(answer, ground_truth) if ground_truth else 0.0,
        )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    ordered = sorted(xs)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[k]


@dataclass
class EvalSummary:
    total: int
    correct: int
    source_hits: int
    citation_correct: int
    accuracy: float
    source_hit_rate: float
    mrr: float
    citation_accuracy: float
    exact_match: float
    token_f1: float
    rouge_l: float
    avg_latency_ms: float
    p95_latency_ms: float
    avg_faithfulness: float | None
    avg_answer_relevancy: float | None
    failures: list[str] = field(default_factory=list)

    @classmethod
    def from_results(cls, results: list[QuestionResult]) -> EvalSummary:
        n = len(results)
        faiths = [r.faithfulness for r in results if r.faithfulness is not None]
        rels = [r.answer_relevancy for r in results if r.answer_relevancy is not None]
        latencies = [r.latency_ms for r in results]
        # Başarısız örnek: yanlış cevap VEYA kaynak ıskası (analiz için).
        failures = [r.id for r in results if not r.is_correct or not r.is_source_hit]
        return cls(
            total=n,
            correct=sum(r.is_correct for r in results),
            source_hits=sum(r.is_source_hit for r in results),
            citation_correct=sum(r.is_citation_correct for r in results),
            accuracy=_mean([float(r.is_correct) for r in results]),
            source_hit_rate=_mean([float(r.is_source_hit) for r in results]),
            mrr=_mean([r.rr for r in results]),
            citation_accuracy=_mean([float(r.is_citation_correct) for r in results]),
            exact_match=_mean([r.em for r in results]),
            token_f1=_mean([r.f1 for r in results]),
            rouge_l=_mean([r.rouge for r in results]),
            avg_latency_ms=_mean(latencies),
            p95_latency_ms=_percentile(latencies, 95),
            avg_faithfulness=_mean(faiths) if faiths else None,
            avg_answer_relevancy=_mean(rels) if rels else None,
            failures=failures,
        )
