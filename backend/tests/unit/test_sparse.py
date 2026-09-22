"""BM25 sparse encoder birim testleri, ağsız/deterministik."""

from __future__ import annotations

from app.ingestion.sparse import Bm25SparseEncoder


def test_encode_is_deterministic() -> None:
    enc = Bm25SparseEncoder()
    a = enc.encode("Kubernetes konteyner orkestrasyonu")
    b = enc.encode("Kubernetes konteyner orkestrasyonu")
    assert a.indices == b.indices
    assert a.values == b.values


def test_encode_indices_and_values_aligned_and_positive() -> None:
    enc = Bm25SparseEncoder()
    sv = enc.encode("FastAPI Python web çerçevesi")
    assert len(sv.indices) == len(sv.values)
    assert sv.indices  # boş değil
    assert all(v > 0 for v in sv.values)
    assert all(0 <= i < 2**31 for i in sv.indices)


def test_repeated_term_merges_into_single_index() -> None:
    enc = Bm25SparseEncoder()
    sv = enc.encode("vektör vektör vektör")
    # Tek anlamlı terim → tek indeks (çakışma/tekrar birleşti)
    assert len(sv.indices) == len(set(sv.indices))
    assert len(sv.indices) == 1


def test_bm25_saturation_caps_high_frequency() -> None:
    enc = Bm25SparseEncoder(k1=1.2)
    once = enc.encode("terim")
    many = enc.encode("terim " * 100)
    # Doygunluk: 100 tekrar, tek tekrarın ağırlığının (k1+1)=2.2 katından azdır.
    assert many.values[0] > once.values[0]
    assert many.values[0] < once.values[0] * (1.2 + 1.0)


def test_stopwords_and_single_chars_removed() -> None:
    enc = Bm25SparseEncoder()
    # yalnızca stopword ve tek harfli token'lar → boş sparse
    assert enc.encode("ve bir ile de a x").indices == []


def test_empty_text_returns_empty() -> None:
    enc = Bm25SparseEncoder()
    sv = enc.encode("   ")
    assert sv.indices == []
    assert sv.values == []


def test_encode_batch_matches_encode() -> None:
    enc = Bm25SparseEncoder()
    texts = ["birinci metin", "ikinci farklı metin"]
    batch = enc.encode_batch(texts)
    assert len(batch) == 2
    assert batch[0].indices == enc.encode(texts[0]).indices
