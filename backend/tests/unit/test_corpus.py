"""Korpus üretimi + golden set bütünlüğü (kendine yeten, ağsız).

Korpus geçici dizine üretilir; testler data/corpus'un diskte var olmasına bağlı
değildir. Golden set'in her beklenen kaynağının üretilen korpusta bulunması,
değerlendirmenin sağlam bir temele oturmasını garanti eder.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_corpus import build

_GOLDEN = Path(__file__).resolve().parent.parent.parent / "evaluation" / "golden_set.jsonl"


def _load_golden() -> list[dict]:
    lines = _GOLDEN.read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines if ln.strip()]


def test_corpus_size_in_target_range(tmp_path: Path) -> None:
    total = build(tmp_path / "corpus")
    files = list((tmp_path / "corpus").rglob("*.md"))
    assert total == len(files)
    assert 100 <= total <= 150  # isterlerdeki 100-150 aralığı


def test_corpus_has_multiple_categories(tmp_path: Path) -> None:
    build(tmp_path / "corpus")
    categories = {p.parent.name for p in (tmp_path / "corpus").rglob("*.md")}
    assert {"frameworks", "infrastructure", "databases", "ai-ml"} <= categories


def test_golden_set_size_and_unique_ids() -> None:
    golden = _load_golden()
    assert len(golden) >= 50  # ister: 50+ soru
    ids = [g["id"] for g in golden]
    assert len(ids) == len(set(ids))


def test_golden_set_schema() -> None:
    for g in _load_golden():
        assert g["question"].strip()
        assert g["expected_source"].endswith(".md")
        assert isinstance(g["expected_keywords"], list) and g["expected_keywords"]
        assert g["ground_truth"].strip()


def test_golden_sources_exist_in_corpus(tmp_path: Path) -> None:
    build(tmp_path / "corpus")
    names = {p.name for p in (tmp_path / "corpus").rglob("*.md")}
    missing = [g["expected_source"] for g in _load_golden() if g["expected_source"] not in names]
    assert not missing, f"Korpusta bulunmayan golden kaynaklar: {missing}"
