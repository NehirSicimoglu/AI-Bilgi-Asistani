"""Referans-tabanlı üretim metrikleri (exact_match, token_f1, rouge_l) — ağsız.

Bu metrikler LLM yargısı içermez; ground_truth ile sistem cevabını kelime
düzeyinde karşılaştırır. Deterministik oldukları için birim testlerle sabitlenir.
"""

from __future__ import annotations

import math

from evaluation.metrics import (
    EvalSummary,
    QuestionResult,
    exact_match,
    rouge_l,
    token_f1,
)


def test_exact_match_normalizes_case_and_punctuation() -> None:
    assert exact_match("Öklid mesafe ölçümü.", "öklid mesafe ölçümü") is True
    assert exact_match("Donanım, 4 adet", "donanım 4 adet") is True
    assert exact_match("Donanım 5 adet", "donanım 4 adet") is False


def test_token_f1_full_and_partial_overlap() -> None:
    assert token_f1("a b c", "a b c") == 1.0
    assert token_f1("x y z", "a b c") == 0.0
    # 2 ortak kelime; pred=3, truth=4 → P=2/3, R=2/4 → F1=0.571...
    f1 = token_f1("ortak kelime fazla", "ortak kelime az yok")
    assert math.isclose(f1, 2 * (2 / 3) * (2 / 4) / ((2 / 3) + (2 / 4)), rel_tol=1e-9)


def test_token_f1_edge_cases() -> None:
    assert token_f1("", "") == 1.0
    assert token_f1("dolu", "") == 0.0
    assert token_f1("", "dolu") == 0.0


def test_rouge_l_rewards_word_order() -> None:
    assert rouge_l("a b c d", "a b c d") == 1.0
    # LCS'yi sıra korur: "a b c" ortak alt dizi (len=3)
    r = rouge_l("a b x c", "a b c y")
    # LCS("a b x c","a b c y")= "a b c" =3; P=3/4,R=3/4 → 0.75
    assert math.isclose(r, 0.75, rel_tol=1e-9)
    assert rouge_l("hiç", "ortak yok burada") == 0.0


def test_summary_aggregates_generation_metrics() -> None:
    r = QuestionResult.build(
        id="q1",
        question="Ürün 37?",
        answer="Ürün 37'nin kategorisi Donanım, stok 4, fiyat 3057.",
        expected_source="Stok.xlsx",
        expected_keywords=["Donanım", "3057"],
        retrieved_sources=["Stok.xlsx"],
        cited_sources=["Stok.xlsx"],
        latency_ms=1000.0,
        ground_truth="Donanım kategorisi, stok 4, birim fiyat 3057.",
    )
    assert 0.0 < r.f1 <= 1.0
    assert 0.0 < r.rouge <= 1.0
    summary = EvalSummary.from_results([r])
    assert summary.token_f1 == r.f1
    assert summary.rouge_l == r.rouge
    assert 0.0 <= summary.exact_match <= 1.0


