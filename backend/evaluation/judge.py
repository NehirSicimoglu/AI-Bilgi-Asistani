"""LLM-yargılı RAG metrikleri — RAGAS'ın kavramsal karşılığı, Gemini ile.

Karar: Gerçek `ragas` (varsayılan OpenAI + LangChain) yerine, mevcut `LLMProvider`
arayüzümüzün arkasındaki Gemini'yi yargıç olarak kullanan hafif bir değerlendirici.
Böylece ağır bağımlılık ve OpenAI zorunluluğu olmadan RAGAS'ın temel fikirleri
(faithfulness, answer relevancy) ölçülür; yargıç modeli `.env` ile takas edilebilir.

- **faithfulness**: cevap, verilen bağlamdan destekleniyor mu? (uydurma cezalandırılır)
- **answer_relevancy**: cevap, soruyla ne kadar ilgili?

Her ikisi de 0..1 arası döner. LLM hatasında None döner (değerlendirme çökmesin).
"""

from __future__ import annotations

import re

from app.exceptions import ProviderError
from app.logging import get_logger
from app.models.domain import Role
from app.providers.llm.base import LLMMessage, LLMProvider

logger = get_logger(__name__)

_SCORE_RE = re.compile(r"[01](?:[.,]\d+)?")

_FAITHFULNESS_SYSTEM = (
    "Bir RAG cevabını değerlendiren tarafsız bir yargıçsın. Sana KAYNAKLAR ve CEVAP "
    "verilecek. Cevaptaki iddiaların ne kadarının KAYNAKLARDAN desteklendiğini ölç. "
    "Yalnızca 0 ile 1 arasında tek bir ondalık sayı yaz (1 = tamamen destekli, "
    "0 = hiç destekli değil). Başka hiçbir şey yazma."
)

_RELEVANCY_SYSTEM = (
    "Bir cevabın soruyla ilgisini değerlendiren tarafsız bir yargıçsın. Sana SORU ve "
    "CEVAP verilecek. Cevabın soruyu ne kadar doğrudan yanıtladığını ölç. Yalnızca 0 "
    "ile 1 arasında tek bir ondalık sayı yaz (1 = tam ilgili, 0 = alakasız). Başka "
    "hiçbir şey yazma."
)


def _parse_score(text: str) -> float | None:
    m = _SCORE_RE.search(text.strip())
    if not m:
        return None
    try:
        value = float(m.group(0).replace(",", "."))
    except ValueError:
        return None
    return max(0.0, min(1.0, value))


class LLMJudge:
    """Gemini (veya herhangi bir LLMProvider) ile faithfulness/relevancy yargısı."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def _score(self, system: str, user: str) -> float | None:
        try:
            resp = await self._llm.generate(
                [LLMMessage(role=Role.USER, content=user)], system=system
            )
        except ProviderError as exc:
            logger.warning("judge_failed", error=str(exc))
            return None
        return _parse_score(resp.text)

    async def faithfulness(self, answer: str, contexts: list[str]) -> float | None:
        joined = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
        user = f"KAYNAKLAR:\n{joined}\n\nCEVAP:\n{answer}\n\nPuan:"
        return await self._score(_FAITHFULNESS_SYSTEM, user)

    async def answer_relevancy(self, question: str, answer: str) -> float | None:
        user = f"SORU:\n{question}\n\nCEVAP:\n{answer}\n\nPuan:"
        return await self._score(_RELEVANCY_SYSTEM, user)
