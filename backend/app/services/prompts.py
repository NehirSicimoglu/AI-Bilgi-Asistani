"""RAG prompt şablonları ve bağlam (context) oluşturma.

Kaynaklar retrieval'dan deterministik gelir ve [1], [2] ... diye numaralandırılır.
LLM'den her bilgiyi aldığı kaynağın numarasını [n] işaretiyle belirtmesi istenir;
bu işaretler citation'ları deterministik olarak eşlemek için kullanılır ve
kullanıcıya gösterilmeden önce servis katmanında metinden temizlenir (bkz.
`chat.py:_strip_markers`). Böylece hem hassas kaynak gösterimi hem de düz, akıcı
bir cevap birlikte elde edilir.
"""

from __future__ import annotations

from app.models.domain import Message, RetrievalResult, Role

SYSTEM_PROMPT = (
    "Sen bir kurum içi bilgi asistanısın. SADECE sana verilen KAYNAKLAR "
    "bölümündeki bilgileri kullanarak cevap ver.\n"
    "Kurallar:\n"
    "- Cevabı yalnızca kaynaklardan üret. Kaynaklarda yoksa aynen şunu yaz: "
    '"Bu konuda yüklenen dokümanlarda bilgi bulamadım."\n'
    "- Her bilgiyi hangi kaynaktan aldıysan, o cümlenin sonuna kaynağın "
    "numarasını [n] biçiminde ekle (örn. [1] veya [2]). Bir cümle birden çok "
    "kaynağa dayanıyorsa hepsini yaz (örn. [1][3]).\n"
    "- Yalnızca KAYNAKLAR bölümünde gerçekten verilen numaraları kullan; "
    "olmayan bir numarayı uydurma.\n"
    "- Kullanıcının dilinde, açık ve öz cevap ver.\n"
    "- Kaynakları veya bilgileri uydurma."
)

NO_CONTEXT_ANSWER = "Bu konuda yüklenen dokümanlarda bilgi bulamadım."


def build_context(results: list[RetrievalResult]) -> str:
    blocks: list[str] = []
    for i, r in enumerate(results, start=1):
        location = r.document_name
        if r.page is not None:
            location += f", s.{r.page}"
        blocks.append(f"[{i}] ({location})\n{r.text}")
    return "\n\n".join(blocks)


def build_user_prompt(query: str, context: str) -> str:
    return f"KAYNAKLAR:\n{context}\n\nSORU: {query}\n\nCevap:"


# --- Çok turlu sohbet: history-aware query rewriting ---------------------------
#
# Takip soruları ("peki ya o?", "detaylandır") tek başına retrieval için anlamsızdır;
# önceki turların bağlamıyla bağımsız (standalone) bir sorguya çevrilir. Böylece
# retrieval her turda doğru chunk'ları bulur. Yeniden yazım BAŞARISIZ olursa
# (LLM hatası/boş çıktı) çağıran taraf özgün soruya güvenle geri döner.

REWRITE_SYSTEM_PROMPT = (
    "Bir sohbet geçmişi ve kullanıcının son sorusu veriliyor. Son soruyu, "
    "geçmişe bakmadan tek başına anlaşılır, bağımsız bir arama sorgusuna çevir.\n"
    "Kurallar:\n"
    "- Zamirleri/eksik özneleri geçmişteki asıl konuyla doldur.\n"
    "- Soru zaten bağımsızsa aynen koru.\n"
    "- Cevap verme, açıklama yapma; SADECE yeniden yazılmış sorguyu tek satırda yaz."
)


def format_history(messages: list[Message]) -> str:
    """Mesaj geçmişini prompt'a gömmek için okunur metne çevirir."""
    lines: list[str] = []
    for m in messages:
        who = "Kullanıcı" if m.role == Role.USER else "Asistan"
        lines.append(f"{who}: {m.content}")
    return "\n".join(lines)


def build_rewrite_prompt(history: list[Message], query: str) -> str:
    return (
        f"SOHBET GEÇMİŞİ:\n{format_history(history)}\n\n"
        f"SON SORU: {query}\n\n"
        "Bağımsız arama sorgusu:"
    )


# --- Query Decomposition: çok-belgeli soruyu alt-sorgulara bölme ----------------
#
# Cevabı birden çok belgeden bilgi birleştirmeyi gerektiren sorular ("A belgesindeki
# X ile B belgesindeki Y'yi karşılaştır") tek arama sorgusuyla getirildiğinde, baskın
# konu üst sıraları doldurur ve ikincil belge hiç gelmeyebilir. Bu prompt, soruyu her
# biri TEK bir bilgi ihtiyacına odaklı bağımsız alt-sorgulara böler; her alt-sorgu ayrı
# getirilir. Soru tek bilgi içeriyorsa bölmeye gerek yoktur (tek satır döner). Bölme
# BAŞARISIZ/boş olursa çağıran taraf özgün soruya güvenle geri döner.

DECOMPOSE_SYSTEM_PROMPT = (
    "Bir kullanıcı sorusunu, arama (retrieval) için bağımsız alt-sorgulara böl.\n"
    "Kurallar:\n"
    "- Soru birden çok ayrı bilgi ihtiyacı içeriyorsa (ör. iki farklı konu/belge, "
    "karşılaştırma, 've' ile bağlı ayrı olgular), her bilgi ihtiyacı için TEK satırlık "
    "bağımsız bir alt-sorgu yaz.\n"
    "- Her alt-sorgu tek başına anlaşılır olmalı; zamir/eksik özne bırakma.\n"
    "- Soru tek bir bilgi içeriyorsa bölme; soruyu tek satırda aynen yaz.\n"
    "- Cevap verme, açıklama/numaralandırma yapma. SADECE alt-sorguları, her biri ayrı "
    "satırda yaz. En fazla {max_subqueries} satır."
)


def build_decompose_prompt(query: str, max_subqueries: int) -> str:
    return (
        f"SORU: {query}\n\n"
        f"Alt-sorgular (en fazla {max_subqueries} satır, her biri ayrı satırda):"
    )
