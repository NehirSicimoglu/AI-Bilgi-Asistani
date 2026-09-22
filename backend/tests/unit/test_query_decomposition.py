"""Query Decomposition — çapraz-belge çoklu-sorgu getirme (ağsız, fake'lerle).

Kapsam:
- `_parse_subqueries`: LLM bölme çıktısını temiz alt-sorgu listesine çevirir.
- `_round_robin_dedup`: alt-sorgu sonuçlarını sıra-sıra birleştirip tekilleştirir.
- `ChatService._decompose_query`: bayrak kapalı/açık, boş ve hata fallback'leri.
- `RetrievalService.retrieve_multi`: paralel getirme + merge; tek alt-sorgu düşüşü.
- `ChatService._run_retrieval`: bölme sonucuna göre retrieve / retrieve_multi dallanması.

Hiçbir gerçek LLM/embedding/Qdrant çağrısı yapılmaz.
"""

from __future__ import annotations

from app.config import Settings
from app.exceptions import ProviderError
from app.models.domain import RetrievalResult, TokenUsage
from app.providers.llm.base import LLMResponse
from app.services.chat import ChatService, _parse_subqueries
from app.services.retrieval import RetrievalService, _round_robin_dedup


def _result(chunk_id: str, document_name: str = "Belge") -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="doc",
        document_name=document_name,
        text="metin",
        score=1.0,
        page=None,
        metadata={},
    )


class _FakeLLM:
    """Sabit metin döndüren ağsız LLM; hata modunda ProviderError fırlatır."""

    def __init__(self, text: str = "", *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.calls: list[str | None] = []

    async def generate(self, messages, *, system=None, model=None, **kwargs):
        self.calls.append(model)
        if self.fail:
            raise ProviderError("boom")
        return LLMResponse(text=self.text, usage=TokenUsage())

    async def stream(self, messages, *, system=None, **kwargs):  # pragma: no cover
        yield self.text


class _FakeRetrieval(RetrievalService):
    """retrieve()'i sahteleyerek retrieve_multi/_round_robin'i ağsız test eder."""

    def __init__(self, settings: Settings, mapping: dict[str, list[RetrievalResult]]):
        self._settings = settings
        self._mapping = mapping
        self.calls: list[tuple[str, int | None]] = []

    async def retrieve(self, query, *, top_k=None, mode=None, filters=None):
        self.calls.append((query, top_k))
        return self._mapping.get(query, [])


# --- _parse_subqueries ---------------------------------------------------------


def test_parse_subqueries_bolme():
    assert _parse_subqueries("Ürün 37 fiyatı\nML platformları", 3) == [
        "Ürün 37 fiyatı",
        "ML platformları",
    ]


def test_parse_subqueries_madde_isareti_ve_ust_sinir():
    assert _parse_subqueries("1) a\n2) b\n- c\n4) d", 3) == ["a", "b", "c"]


def test_parse_subqueries_tekrar_eler():
    assert _parse_subqueries("Soru\nsoru", 3) == ["Soru"]


def test_parse_subqueries_bos_ve_bosluk():
    assert _parse_subqueries("", 3) == []
    assert _parse_subqueries("\n   \n", 3) == []


# --- _round_robin_dedup --------------------------------------------------------


def test_round_robin_sira_ve_dedup():
    lists = [
        [_result("a1"), _result("a2"), _result("ortak")],
        [_result("b1"), _result("b2"), _result("ortak")],
    ]
    merged = _round_robin_dedup(lists)
    assert [r.chunk_id for r in merged] == ["a1", "b1", "a2", "b2", "ortak"]
    assert [r.chunk_id for r in merged].count("ortak") == 1


def test_round_robin_bos_ve_dengesiz():
    assert _round_robin_dedup([]) == []
    merged = _round_robin_dedup([[_result("x")], [_result("y1"), _result("y2")]])
    assert [r.chunk_id for r in merged] == ["x", "y1", "y2"]


# --- ChatService._decompose_query ---------------------------------------------


async def test_decompose_bayrak_kapali_llm_cagirmaz():
    llm = _FakeLLM("alt1\nalt2")  # açık olsa bölerdi
    svc = ChatService(
        settings=Settings(enable_query_decomposition=False), retrieval=None, llm=llm
    )
    assert await svc._decompose_query("çok parçalı soru") == ["çok parçalı soru"]
    assert llm.calls == []  # bayrak kapalı → LLM'e hiç dokunulmaz


async def test_decompose_bayrak_acik_boler():
    llm = _FakeLLM("Ürün 37 fiyatı\nMakine öğrenmesi platformları")
    svc = ChatService(
        settings=Settings(enable_query_decomposition=True), retrieval=None, llm=llm
    )
    result = await svc._decompose_query("Ürün 37 ve ML platformları")
    assert result == ["Ürün 37 fiyatı", "Makine öğrenmesi platformları"]
    # Ana model değil, hafif rewrite modeli kullanılmalı.
    assert llm.calls == [Settings().llm_rewrite_model]


async def test_decompose_bos_cikti_fallback():
    svc = ChatService(
        settings=Settings(enable_query_decomposition=True),
        retrieval=None,
        llm=_FakeLLM("   "),
    )
    assert await svc._decompose_query("orijinal") == ["orijinal"]


async def test_decompose_llm_hatasi_fallback():
    svc = ChatService(
        settings=Settings(enable_query_decomposition=True),
        retrieval=None,
        llm=_FakeLLM(fail=True),
    )
    assert await svc._decompose_query("orijinal") == ["orijinal"]


# --- RetrievalService.retrieve_multi ------------------------------------------


async def test_retrieve_multi_merge_ve_dedup():
    settings = Settings(enable_query_decomposition=True)
    fr = _FakeRetrieval(
        settings,
        {
            "stok": [_result("s1", "Stok"), _result("ortak")],
            "ml": [_result("m1", "ML"), _result("ortak")],
        },
    )
    merged = await fr.retrieve_multi(["stok", "ml"], top_k=2)
    assert [r.chunk_id for r in merged] == ["s1", "m1", "ortak"]
    assert fr.calls == [("stok", 2), ("ml", 2)]  # her alt-sorgu verilen top_k ile


async def test_retrieve_multi_tek_alt_sorgu_normal_retrieve():
    settings = Settings(enable_query_decomposition=True)  # subquery_top_k=3
    fr = _FakeRetrieval(settings, {"stok": [_result("s1")]})
    merged = await fr.retrieve_multi(["stok"])
    assert [r.chunk_id for r in merged] == ["s1"]
    assert fr.calls == [("stok", 3)]  # subquery_top_k'ye düşer


# --- ChatService._run_retrieval (dallanma) ------------------------------------


async def test_run_retrieval_kapaliyken_normal_yol():
    settings = Settings(enable_query_decomposition=False)
    fr = _FakeRetrieval(settings, {"soru": [_result("single")]})
    svc = ChatService(settings=settings, retrieval=fr, llm=_FakeLLM("alt1\nalt2"))
    results = await svc._run_retrieval("soru", top_k=5, mode="hybrid", filters=None)
    assert [r.chunk_id for r in results] == ["single"]
    assert fr.calls == [("soru", 5)]  # top_k korunur, retrieve_multi'ye gitmez


async def test_run_retrieval_acik_coklu_multi_yol():
    settings = Settings(enable_query_decomposition=True)
    fr = _FakeRetrieval(
        settings, {"alt1": [_result("m1")], "alt2": [_result("m2")]}
    )
    svc = ChatService(settings=settings, retrieval=fr, llm=_FakeLLM("alt1\nalt2"))
    results = await svc._run_retrieval(
        "birleşik", top_k=5, mode="hybrid", filters=None
    )
    assert [r.chunk_id for r in results] == ["m1", "m2"]
    # Çoklu yolda alt-sorgular subquery_top_k (3) ile getirilir, orijinal top_k değil.
    assert fr.calls == [("alt1", 3), ("alt2", 3)]


async def test_run_retrieval_acik_tek_bilgi_normal_yol():
    settings = Settings(enable_query_decomposition=True)
    fr = _FakeRetrieval(settings, {"tek soru": [_result("single")]})
    svc = ChatService(settings=settings, retrieval=fr, llm=_FakeLLM("tek soru"))
    results = await svc._run_retrieval(
        "tek soru", top_k=5, mode="hybrid", filters=None
    )
    assert [r.chunk_id for r in results] == ["single"]
    assert fr.calls == [("tek soru", 5)]  # tek alt-sorgu → normal retrieve + top_k
