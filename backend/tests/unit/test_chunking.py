"""Chunking testleri."""

from __future__ import annotations

from app.ingestion.chunking import chunk_document, chunk_text, count_tokens
from app.ingestion.parsers import ParsedDocument, ParsedPage


def test_short_text_single_chunk() -> None:
    chunks = chunk_text("Kısa bir metin.", chunk_size=100, overlap=10)
    assert len(chunks) == 1
    assert "Kısa" in chunks[0]


def test_long_text_multiple_chunks_respecting_size() -> None:
    text = " ".join(f"cümle{i} bazı içerik burada." for i in range(400))
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    for c in chunks:
        # Overlap birleşimi nedeniyle küçük taşmalara tolerans
        assert count_tokens(c) <= 160


def test_chunks_have_overlap() -> None:
    text = " ".join(f"kelime{i}" for i in range(300))
    chunks = chunk_text(text, chunk_size=60, overlap=20)
    assert len(chunks) >= 2
    # ardışık chunk'lar arasında ortak kelime bulunmalı (overlap)
    first_words = set(chunks[0].split())
    second_words = set(chunks[1].split())
    assert first_words & second_words


def test_chunk_document_preserves_page_and_metadata() -> None:
    parsed = ParsedDocument(
        pages=[
            ParsedPage(page=1, text="Birinci sayfa. " * 50),
            ParsedPage(page=2, text="Ikinci sayfa. " * 50),
        ]
    )
    chunks = chunk_document(
        parsed,
        document_id="doc1",
        chunk_size=50,
        chunk_overlap=10,
        base_metadata={"document_name": "x.pdf", "category": "test"},
    )
    assert chunks
    assert all(c.document_id == "doc1" for c in chunks)
    assert {c.page for c in chunks} == {1, 2}
    assert chunks[0].metadata["document_name"] == "x.pdf"
    # index artan ve benzersiz
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_empty_pages_skipped() -> None:
    parsed = ParsedDocument(pages=[ParsedPage(page=None, text="   ")])
    assert chunk_document(parsed, document_id="d", chunk_size=50, chunk_overlap=10) == []
