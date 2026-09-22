"""Token-aware recursive chunking.

Metni önce anlamsal ayraçlarla (paragraf → satır → cümle → kelime) parçalar,
sonra bu parçaları `chunk_size` token'ı aşmayacak şekilde, `chunk_overlap` kadar
örtüşmeyle birleştirir. Her chunk sayfa numarasını taşır — citation'da kaynağın
kaçıncı sayfadan geldiğini gösterebilmek için.

Token sayımı tiktoken (cl100k_base) ile yaklaşık yapılır; Gemini'nin tokenizer'ı
birebir aynı olmasa da chunk boyutu kararı için yeterince tutarlıdır.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken

from app.ingestion.parsers import ParsedDocument
from app.models.domain import Chunk

_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]


@lru_cache(maxsize=1)
def _encoding():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def _split_recursive(text: str, separators: list[str], chunk_size: int) -> list[str]:
    """Metni, her parçası mümkünse `chunk_size` token'ı aşmayacak şekilde böler."""
    if count_tokens(text) <= chunk_size:
        return [text] if text else []

    sep = separators[-1]
    rest = separators[-1:]
    for i, candidate in enumerate(separators):
        if candidate == "":
            sep = ""
            rest = []
            break
        if candidate in text:
            sep = candidate
            rest = separators[i + 1 :]
            break

    if sep == "":
        # Ayraç kalmadı: token bazında zorla böl
        enc = _encoding()
        tokens = enc.encode(text)
        return [
            enc.decode(tokens[i : i + chunk_size])
            for i in range(0, len(tokens), chunk_size)
        ]

    parts = text.split(sep)
    out: list[str] = []
    for part in parts:
        piece = part + sep
        if count_tokens(piece) <= chunk_size:
            out.append(piece)
        else:
            out.extend(_split_recursive(piece, rest, chunk_size))
    return [p for p in out if p.strip()]


def _merge(splits: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Küçük parçaları chunk_size'a kadar birleştirir; overlap kadar örtüşme bırakır."""
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for part in splits:
        part_tokens = count_tokens(part)
        if current and current_tokens + part_tokens > chunk_size:
            chunks.append("".join(current).strip())
            # Overlap: sondan itibaren overlap token kadar parça taşı
            while current and current_tokens > overlap:
                removed = current.pop(0)
                current_tokens -= count_tokens(removed)
        current.append(part)
        current_tokens += part_tokens

    if current:
        tail = "".join(current).strip()
        if tail:
            chunks.append(tail)
    return chunks


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    splits = _split_recursive(text, _SEPARATORS, chunk_size)
    return _merge(splits, chunk_size, overlap)


def chunk_document(
    parsed: ParsedDocument,
    *,
    document_id: str,
    chunk_size: int,
    chunk_overlap: int,
    base_metadata: dict | None = None,
) -> list[Chunk]:
    """Parse edilmiş dokümanı, sayfa/offset metadata'sı taşıyan Chunk listesine çevirir."""
    base_metadata = base_metadata or {}
    chunks: list[Chunk] = []
    index = 0

    for page in parsed.pages:
        if not page.text.strip():
            continue
        for piece in chunk_text(page.text, chunk_size, chunk_overlap):
            chunks.append(
                Chunk(
                    document_id=document_id,
                    index=index,
                    text=piece.strip(),
                    page=page.page,
                    metadata={**base_metadata},
                )
            )
            index += 1

    return chunks
