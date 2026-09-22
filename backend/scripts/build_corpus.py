"""SADECE İÇ TEST FIXTURE'I — bu, uygulamanın gerçek/üretim veri seti DEĞİLDİR.

Gerçek bilgi tabanı, gerçek dokümanlardan (resmi ürün dokümantasyonları, Hugging
Face model kartları, LangChain/Qdrant/Chroma dokümantasyonu vb.) oluşturulur ve
frontend (veya POST /documents) üzerinden kullanıcı tarafından yüklenir.

Bu betik yalnızca `tests/unit/test_corpus.py` ve `evaluation/golden_set.jsonl`
için ağsız, deterministik, tekrarlanabilir bir DEV/TEST veri kümesi üretir —
korpus üretim → ingestion → hybrid retrieval → evaluation zincirinin uçtan uca
doğru çalıştığını, gerçek dosyalara ve ağa bağımlı olmadan pytest'te kanıtlamak
içindir.

Her konu 3 doküman üretir (genel bakış / SSS / nasıl-yapılır) ve her sözlük terimi
1 kısa doküman → toplam ~100+. Kategoriler klasör adından türetilir.

Çalıştırma (yalnızca test/geliştirme amaçlı):
    uv run python -m scripts.build_corpus  [--out data/corpus]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

# --- Gömülü bilgi tabanı --------------------------------------------------------
# Her konu: (slug, başlık, kategori, özet, gerçekler, SSS[(s,c)], adımlar[])

TOPICS: list[dict] = [
    {
        "slug": "fastapi",
        "title": "FastAPI",
        "category": "frameworks",
        "summary": "FastAPI, Python tip ipuçlarına dayanan modern, yüksek performanslı bir web çerçevesidir. Otomatik veri doğrulama ve OpenAPI dokümantasyonu sağlar.",
        "facts": [
            "FastAPI, istek/yanıt şemaları için Pydantic modellerini kullanır ve gövdeyi otomatik doğrular.",
            "ASGI tabanlıdır; async/await ile eşzamanlı I/O'yu yerel olarak destekler.",
            "Uç noktalardan Swagger UI ve ReDoc arayüzlü OpenAPI şeması otomatik üretilir.",
            "Bağımlılık enjeksiyonu `Depends` ile sağlanır; test için kolayca override edilir.",
        ],
        "faq": [
            ("FastAPI hangi sunucuyla çalıştırılır?", "Uvicorn veya Hypercorn gibi bir ASGI sunucusuyla; geliştirmede genelde Uvicorn kullanılır."),
            ("FastAPI veri doğrulamayı nasıl yapar?", "Pydantic modelleriyle; gelen JSON otomatik olarak tiplere göre doğrulanır ve hatalıysa 422 döner."),
            ("Streaming yanıt mümkün mü?", "Evet, StreamingResponse ile; Server-Sent Events veya parça parça gövde akışı desteklenir."),
        ],
        "steps": [
            "pyproject veya requirements ile fastapi ve uvicorn bağımlılıklarını ekleyin.",
            "Bir APIRouter veya FastAPI örneği oluşturup uç noktaları tanımlayın.",
            "İstek/yanıt için Pydantic şemaları yazın.",
            "`uvicorn app.main:app --reload` ile çalıştırın ve /docs adresinden test edin.",
        ],
    },
    {
        "slug": "pydantic",
        "title": "Pydantic",
        "category": "frameworks",
        "summary": "Pydantic, Python tip ipuçlarıyla veri doğrulama ve ayrıştırma yapan bir kütüphanedir. v2 çekirdeği Rust ile yazılmıştır ve hızlıdır.",
        "facts": [
            "Pydantic modelleri BaseModel'den türetilir ve alan tiplerini çalışma zamanında zorlar.",
            "pydantic-settings, ortam değişkenlerinden (.env) yapılandırma okumayı sağlar.",
            "Doğrulama başarısızsa ValidationError fırlatır ve ayrıntılı hata listesi verir.",
            "model_dump() ve model_validate() ile serileştirme/ayrıştırma yapılır.",
        ],
        "faq": [
            ("Pydantic v2 v1'den farkı nedir?", "v2 çekirdeği Rust ile yeniden yazıldı; daha hızlıdır ve API'de model_dump gibi yeni adlar kullanır."),
            ("Ayarları .env'den nasıl okurum?", "pydantic-settings paketindeki BaseSettings ile; alanlar ortam değişkenlerine eşlenir."),
            ("Varsayılan değer nasıl verilir?", "Alan tipine doğrudan atama ya da Field(default=...) ile."),
        ],
        "steps": [
            "pydantic ve gerekiyorsa pydantic-settings kurun.",
            "BaseModel'den türeyen bir sınıf tanımlayıp alanları tiple belirtin.",
            "Girdi verisini model_validate ile doğrulayın.",
            "Çıktı için model_dump ile sözlüğe/JSON'a çevirin.",
        ],
    },
    {
        "slug": "sqlalchemy",
        "title": "SQLAlchemy",
        "category": "frameworks",
        "summary": "SQLAlchemy, Python için bir ORM ve SQL araç setidir. 2.0 sürümü async oturumları ve tiplenmiş ORM eşlemelerini destekler.",
        "facts": [
            "SQLAlchemy 2.0 async motoru create_async_engine ile kurulur ve asyncpg gibi bir sürücü gerektirir.",
            "Mapped ve mapped_column ile tiplenmiş ORM sınıfları tanımlanır.",
            "AsyncSession, veritabanı işlemlerini await ile yürütür.",
            "İlişkiler relationship ile tanımlanır ve cascade seçenekleriyle silme davranışı ayarlanır.",
        ],
        "faq": [
            ("Async için hangi sürücü gerekir?", "PostgreSQL için asyncpg; motor URL'si postgresql+asyncpg ile başlar."),
            ("Şema göçlerini nasıl yönetirim?", "Alembic ile; autogenerate göçleri ORM modellerinden üretir."),
            ("expire_on_commit ne işe yarar?", "Commit sonrası nesnelerin tazelenip tazelenmeyeceğini belirler; False ile veriler erişilebilir kalır."),
        ],
        "steps": [
            "create_async_engine ile motoru kurun.",
            "async_sessionmaker ile oturum fabrikası oluşturun.",
            "DeclarativeBase'den türeyen ORM modelleri tanımlayın.",
            "AsyncSession içinde sorgularınızı await ile çalıştırın.",
        ],
    },
    {
        "slug": "alembic",
        "title": "Alembic",
        "category": "frameworks",
        "summary": "Alembic, SQLAlchemy için veritabanı şema göç (migration) aracıdır. Sürümlenmiş göç dosyalarıyla şemayı ileri/geri alır.",
        "facts": [
            "alembic revision --autogenerate, ORM modelleri ile mevcut şema arasındaki farktan göç üretir.",
            "alembic upgrade head göçleri en son sürüme uygular.",
            "Her göç dosyasında upgrade ve downgrade fonksiyonları bulunur.",
            "env.py, hedef metadata'yı ve bağlantıyı yapılandırır.",
        ],
        "faq": [
            ("Autogenerate her değişikliği yakalar mı?", "Çoğu şema değişikliğini yakalar ama bazı durumları elle düzeltmek gerekir."),
            ("Göç nasıl geri alınır?", "alembic downgrade -1 ile bir sürüm geri alınır."),
            ("Birden çok baş (head) olursa?", "alembic merge ile başlar birleştirilir."),
        ],
        "steps": [
            "alembic init ile göç dizinini oluşturun.",
            "env.py içinde target_metadata'yı modellerinize bağlayın.",
            "alembic revision --autogenerate -m 'mesaj' ile göç üretin.",
            "alembic upgrade head ile uygulayın.",
        ],
    },
    {
        "slug": "docker",
        "title": "Docker",
        "category": "infrastructure",
        "summary": "Docker, uygulamaları taşınabilir konteynerlerde paketleyen bir platformdur. İmajlar Dockerfile'dan katmanlı olarak üretilir.",
        "facts": [
            "Bir imaj Dockerfile'daki talimatlardan katman katman oluşturulur.",
            "Çok aşamalı (multi-stage) yapı, derleme araçlarını nihai imajdan ayırarak boyutu küçültür.",
            "Konteynerler izole süreçlerdir; kaynak ve ağ ad alanlarıyla ayrılır.",
            ".dockerignore, imaja gereksiz dosyaların kopyalanmasını engeller.",
        ],
        "faq": [
            ("İmaj ile konteyner farkı nedir?", "İmaj salt-okunur şablondur; konteyner o imajın çalışan bir örneğidir."),
            ("İmaj boyutunu nasıl küçültürüm?", "Çok aşamalı yapı, ince temel imaj (slim/alpine) ve .dockerignore kullanarak."),
            ("Veriyi kalıcı kılmak için ne kullanılır?", "Volume'lar; konteyner silinse de veri korunur."),
        ],
        "steps": [
            "Uygulama için bir Dockerfile yazın.",
            "docker build -t ad:etiket . ile imajı üretin.",
            "docker run ile konteyneri başlatın.",
            "Gerekirse volume ve port eşlemelerini tanımlayın.",
        ],
    },
    {
        "slug": "docker-compose",
        "title": "Docker Compose",
        "category": "infrastructure",
        "summary": "Docker Compose, çok konteynerli uygulamaları tek bir YAML dosyasıyla tanımlayıp yönetir. Tek komutla tüm yığını ayağa kaldırır.",
        "facts": [
            "docker-compose.yml, servisleri, ağları ve volume'ları bildirimsel olarak tanımlar.",
            "docker compose up tüm servisleri başlatır; -d ile arka planda çalıştırır.",
            "depends_on servis başlatma sırasını belirtir ama sağlık durumunu garanti etmez.",
            "Ortam değişkenleri environment veya env_file ile verilir.",
        ],
        "faq": [
            ("Tek komutla nasıl ayağa kaldırılır?", "docker compose up ile; --build imajları yeniden derler."),
            ("Servisler birbirine nasıl erişir?", "Aynı ağdaki servisler birbirine servis adıyla DNS üzerinden erişir."),
            ("Sağlık kontrolü nasıl beklenir?", "healthcheck tanımlayıp depends_on condition: service_healthy kullanarak."),
        ],
        "steps": [
            "Servisleri docker-compose.yml içinde tanımlayın.",
            "Volume ve ağları bildirin.",
            "docker compose up -d ile başlatın.",
            "docker compose logs ile durumu izleyin.",
        ],
    },
    {
        "slug": "kubernetes",
        "title": "Kubernetes",
        "category": "infrastructure",
        "summary": "Kubernetes, konteyner iş yüklerini otomatik dağıtan, ölçekleyen ve yöneten bir orkestrasyon platformudur. İstenen durumu sürekli uzlaştırır.",
        "facts": [
            "Pod, Kubernetes'te dağıtılabilir en küçük birimdir ve bir veya daha çok konteyner içerir.",
            "Deployment, Pod'ların istenen kopya sayısını korur ve güncellemeleri yönetir.",
            "Service, Pod'lara kararlı bir ağ adresi ve yük dengeleme sağlar.",
            "Kubernetes, istenen durumu denetim döngüleriyle (controllers) sürekli uzlaştırır.",
        ],
        "faq": [
            ("Pod ile konteyner farkı nedir?", "Pod bir soyutlamadır; içinde ağ ve depolamayı paylaşan bir veya daha çok konteyner barındırır."),
            ("Uygulama nasıl ölçeklenir?", "Deployment kopya sayısını artırarak veya HorizontalPodAutoscaler ile otomatik."),
            ("Dışarıya nasıl açılır?", "Service (LoadBalancer/NodePort) veya Ingress ile."),
        ],
        "steps": [
            "Uygulamayı bir imaj olarak kayıt defterine gönderin.",
            "Deployment manifesti yazıp kopya sayısını belirtin.",
            "Bir Service ile erişimi tanımlayın.",
            "kubectl apply -f ile küme üzerine uygulayın.",
        ],
    },
    {
        "slug": "prometheus",
        "title": "Prometheus",
        "category": "infrastructure",
        "summary": "Prometheus, çekme (pull) modeliyle zaman serisi metrikleri toplayan bir izleme sistemidir. PromQL ile sorgulama yapılır.",
        "facts": [
            "Prometheus, hedeflerin /metrics ucundan metrikleri periyodik olarak çeker.",
            "Dört temel metrik tipi vardır: Counter, Gauge, Histogram ve Summary.",
            "PromQL, zaman serilerini sorgulamak ve toplamak için kullanılır.",
            "Alertmanager ile eşik tabanlı uyarılar yönetilir.",
        ],
        "faq": [
            ("Counter ile Gauge farkı nedir?", "Counter yalnızca artar (örn. istek sayısı); Gauge artıp azalabilir (örn. bellek)."),
            ("Latency nasıl ölçülür?", "Histogram ile; kova (bucket) sınırlarına göre gecikme dağılımı toplanır."),
            ("Uygulamamı nasıl enstrümante ederim?", "prometheus-client ile metrik tanımlayıp /metrics ucunu açarak."),
        ],
        "steps": [
            "Uygulamada prometheus-client ile metrikleri tanımlayın.",
            "/metrics HTTP ucunu yayınlayın.",
            "prometheus.yml içinde hedefi (scrape target) tanımlayın.",
            "PromQL ile sorgulayıp gösterge panosuna bağlayın.",
        ],
    },
    {
        "slug": "postgresql",
        "title": "PostgreSQL",
        "category": "databases",
        "summary": "PostgreSQL, güçlü, açık kaynaklı bir ilişkisel veritabanıdır. ACID işlemleri, JSONB ve zengin indeksleme sağlar.",
        "facts": [
            "PostgreSQL ACID uyumludur ve çok sürümlü eşzamanlılık denetimi (MVCC) kullanır.",
            "JSONB tipi, yarı yapılandırılmış veriyi indekslenebilir biçimde saklar.",
            "B-tree, GIN ve GiST gibi farklı indeks türlerini destekler.",
            "asyncpg, Python için yüksek performanslı bir async PostgreSQL sürücüsüdür.",
        ],
        "faq": [
            ("JSONB ile JSON farkı nedir?", "JSONB ikili ve indekslenebilir biçimde saklanır; JSON metinsel saklanır ve daha yavaş sorgulanır."),
            ("MVCC ne sağlar?", "Okuyucuların yazıcıları engellememesini; her işlem tutarlı bir anlık görüntü görür."),
            ("Tam metin arama var mı?", "Evet, tsvector ve GIN indeksleriyle yerleşik tam metin arama sağlanır."),
        ],
        "steps": [
            "Veritabanı ve kullanıcıyı oluşturun.",
            "Tabloları ve uygun indeksleri tanımlayın.",
            "Bağlantı havuzu (pool) ile uygulamayı bağlayın.",
            "Sorguları EXPLAIN ANALYZE ile ölçüp optimize edin.",
        ],
    },
    {
        "slug": "qdrant",
        "title": "Qdrant",
        "category": "databases",
        "summary": "Qdrant, benzerlik araması için tasarlanmış açık kaynaklı bir vektör veritabanıdır. Dense ve sparse vektörleri, filtreleme ve hibrit aramayı destekler.",
        "facts": [
            "Qdrant, noktaları (points) dense vektör, isteğe bağlı sparse vektör ve payload ile saklar.",
            "Named vector desteğiyle bir koleksiyonda hem dense hem sparse vektör tutulabilir.",
            "Query API, prefetch ve FusionQuery ile sunucu tarafında RRF hibrit füzyonu yapar.",
            "Payload alanları üzerinde eşitlik, çoklu değer ve aralık (range) filtreleri uygulanabilir.",
        ],
        "faq": [
            ("Hibrit arama nasıl çalışır?", "Dense ve sparse (BM25) aday listeleri prefetch ile alınır ve RRF ile birleştirilir."),
            ("Sparse vektörde IDF nasıl uygulanır?", "SparseVectorParams modifier=IDF ile; IDF sunucu tarafında hesaplanır."),
            ("Metadata filtresi mümkün mü?", "Evet, payload üzerinde must/should koşullarıyla filtreleme yapılır."),
        ],
        "steps": [
            "Koleksiyonu dense + named sparse vektörle oluşturun.",
            "Noktaları vektör ve payload ile upsert edin.",
            "Dense veya hibrit modda query_points ile arayın.",
            "Gerekirse payload filtreleriyle sonuçları daraltın.",
        ],
    },
    {
        "slug": "redis",
        "title": "Redis",
        "category": "databases",
        "summary": "Redis, bellek içi bir anahtar-değer veri deposudur. Önbellek, kuyruk ve oturum saklama için yaygın kullanılır.",
        "facts": [
            "Redis veriyi bellekte tutar; bu yüzden çok düşük gecikme sağlar.",
            "String, list, set, hash ve sorted set gibi veri yapılarını destekler.",
            "RDB anlık görüntü ve AOF günlüğü ile kalıcılık seçenekleri sunar.",
            "Pub/Sub ve stream yapılarıyla mesajlaşma senaryolarını destekler.",
        ],
        "faq": [
            ("Redis kalıcı mıdır?", "Varsayılan bellek içidir ama RDB/AOF ile diske kalıcılık sağlanabilir."),
            ("Önbellek süresi nasıl verilir?", "Anahtara TTL (EXPIRE) atanarak; süre dolunca anahtar silinir."),
            ("Kuyruk olarak kullanılır mı?", "Evet, list veya stream yapılarıyla iş kuyruğu kurulabilir."),
        ],
        "steps": [
            "Redis sunucusunu başlatın.",
            "İstemciyle bağlanıp anahtar-değer yazın.",
            "Önbellek anahtarlarına uygun TTL verin.",
            "Gerekirse pub/sub veya stream ile mesajlaşın.",
        ],
    },
    {
        "slug": "rag",
        "title": "RAG (Retrieval-Augmented Generation)",
        "category": "ai-ml",
        "summary": "RAG, bir dil modelinin cevabını harici belgelerden getirilen bağlamla zenginleştiren bir yaklaşımdır. Halüsinasyonu azaltır ve kaynak gösterimini mümkün kılar.",
        "facts": [
            "RAG akışı genelde parse, chunk, embed, index ve retrieve adımlarından oluşur.",
            "Getirilen bağlam prompt'a eklenir ve model yalnızca bu bağlamdan cevap üretmeye yönlendirilir.",
            "Kaynak gösterimi (citation), cevabı getirilen chunk'lara bağlayarak doğrulanabilirlik sağlar.",
            "RAG, modeli yeniden eğitmeden güncel ve alana özgü bilgi eklemenin ucuz bir yoludur.",
        ],
        "faq": [
            ("RAG halüsinasyonu neden azaltır?", "Model, serbest belleği yerine getirilen gerçek belgelere dayanarak cevap üretir."),
            ("Citation nasıl güvenilir kılınır?", "Kaynaklar retrieval'dan deterministik gelir; model yalnızca hangi kaynağa atıf yaptığını işaretler."),
            ("Streaming ile citation nasıl birleşir?", "Kaynaklar baştan gönderilir; token'lar akarken kesin atıflar akış sonunda hesaplanır."),
        ],
        "steps": [
            "Belgeleri parse edip chunk'lara bölün.",
            "Chunk'ları embed edip vektör veritabanına indeksleyin.",
            "Sorguyu embed edip ilgili chunk'ları getirin.",
            "Bağlamı prompt'a ekleyip modelden citation'lı cevap isteyin.",
        ],
    },
    {
        "slug": "embeddings",
        "title": "Embeddings (Gömme Vektörleri)",
        "category": "ai-ml",
        "summary": "Embedding, metni anlamsal bir sayısal vektöre dönüştüren temsildir. Benzer anlamlı metinler vektör uzayında birbirine yakın konumlanır.",
        "facts": [
            "Embedding modelleri metni sabit boyutlu bir dense vektöre dönüştürür.",
            "Anlamsal benzerlik genellikle kosinüs benzerliğiyle ölçülür.",
            "Aynı embedding modeli hem belge hem sorgu için tutarlı biçimde kullanılmalıdır.",
            "Boyut indirgeme (örn. MRL) vektör boyutunu azaltarak depolama ve hızdan kazandırır.",
        ],
        "faq": [
            ("Benzerlik nasıl ölçülür?", "Çoğunlukla kosinüs benzerliği ile; normalize vektörlerde nokta çarpımı yeterlidir."),
            ("Neden aynı model kullanılmalı?", "Belge ve sorgu vektörleri aynı uzayda olmalı ki mesafeler anlamlı olsun."),
            ("Boyut önemli mi?", "Evet; daha yüksek boyut daha fazla bilgi ama daha çok depolama/hesap demektir."),
        ],
        "steps": [
            "Bir embedding modeli ve boyutu seçin.",
            "Belge chunk'larını toplu (batch) olarak embed edin.",
            "Vektörleri boyutuyla uyumlu bir koleksiyona indeksleyin.",
            "Sorguyu aynı modelle embed edip arayın.",
        ],
    },
    {
        "slug": "vector-search",
        "title": "Vektör Arama (ANN)",
        "category": "ai-ml",
        "summary": "Vektör arama, bir sorgu vektörüne en yakın vektörleri bulma işlemidir. Ölçek için yaklaşık en yakın komşu (ANN) algoritmaları kullanılır.",
        "facts": [
            "Tam (brute-force) arama küçük veri için doğru ama büyük veride yavaştır.",
            "HNSW, grafik tabanlı popüler bir yaklaşık en yakın komşu (ANN) algoritmasıdır.",
            "top_k parametresi döndürülecek en yakın sonuç sayısını belirler.",
            "ANN'de hız ve doğruluk arasında ayarlanabilir bir ödünleşim vardır.",
        ],
        "faq": [
            ("ANN neden gerekir?", "Milyonlarca vektörde tam arama pahalıdır; ANN yeterli doğrulukla çok hızlıdır."),
            ("HNSW nedir?", "Katmanlı bir komşuluk grafiği üzerinde gezinerek yakın komşuları hızlı bulan bir yöntemdir."),
            ("top_k neyi etkiler?", "Kaç sonuç döneceğini; RAG'de bağlam genişliğini ve gürültüyü etkiler."),
        ],
        "steps": [
            "Vektörleri bir ANN indeksine (örn. HNSW) yükleyin.",
            "İndeks parametrelerini hız/doğruluk için ayarlayın.",
            "Sorgu vektörüyle top_k araması yapın.",
            "Sonuçları skora göre sıralayıp kullanın.",
        ],
    },
    {
        "slug": "hybrid-bm25",
        "title": "Hibrit Arama ve BM25",
        "category": "ai-ml",
        "summary": "Hibrit arama, dense anlamsal aramayı BM25 gibi seyrek sözcük tabanlı aramayla birleştirir. İki listenin sonuçları çoğu zaman RRF ile kaynaştırılır.",
        "facts": [
            "BM25, terim frekansı ve ters belge frekansına (IDF) dayanan seyrek (sparse) bir sıralama fonksiyonudur.",
            "Dense arama anlamı, sparse arama tam sözcük eşleşmesini yakalar; hibrit ikisini birleştirir.",
            "RRF (Reciprocal Rank Fusion), sıralama konumlarına göre listeleri skor bağımsız birleştirir.",
            "BM25'te k1 terim frekansı doygunluğunu, b belge uzunluğu normalizasyonunu kontrol eder.",
        ],
        "faq": [
            ("Hibrit neden dense'ten iyi olabilir?", "Nadir anahtar kelimeleri ve tam eşleşmeleri dense kaçırabilir; BM25 bunları yakalar."),
            ("RRF nasıl çalışır?", "Her listedeki sıraya 1/(k+rank) ağırlığı verir ve toplar; skor ölçekleri önemsizleşir."),
            ("k1 parametresi ne yapar?", "Terim frekansının etkisinin ne kadar hızlı doyacağını belirler."),
        ],
        "steps": [
            "Belgeleri hem dense hem sparse (BM25) vektörle indeksleyin.",
            "Sorgu için her iki temsili de üretin.",
            "İki aday listeyi prefetch ile alın.",
            "RRF füzyonuyla nihai sıralamayı oluşturun.",
        ],
    },
    {
        "slug": "chunking",
        "title": "Chunking (Parçalama)",
        "category": "ai-ml",
        "summary": "Chunking, uzun belgeleri embedding ve retrieval için yönetilebilir parçalara bölme işlemidir. Parça boyutu ve örtüşme, retrieval kalitesini doğrudan etkiler.",
        "facts": [
            "Çok büyük chunk'lar gürültü katar; çok küçük chunk'lar bağlamı böler.",
            "Örtüşme (overlap), sınırlarda anlam kaybını azaltmak için komşu chunk'lara bağlam taşır.",
            "Token tabanlı parçalama, model bağlam sınırlarına uyum için tercih edilir.",
            "Chunk metadata'sı (sayfa, offset) citation ve filtreleme için taşınır.",
        ],
        "faq": [
            ("İyi bir chunk boyutu nedir?", "Genelde birkaç yüz token; içerik ve modele göre deneyle ayarlanır."),
            ("Örtüşme neden gerekir?", "Bir cümlenin iki chunk arasında bölünmesiyle oluşan bağlam kaybını azaltır."),
            ("Metadata neden chunk'ta tutulur?", "Citation ve metadata filtrelemesi için kaynak/sayfa bilgisi gerekir."),
        ],
        "steps": [
            "Belgeyi parse edip düz metne çevirin.",
            "Token tabanlı bir bölücüyle chunk'lara ayırın.",
            "Uygun bir örtüşme oranı belirleyin.",
            "Her chunk'a kaynak metadata'sını ekleyin.",
        ],
    },
    {
        "slug": "prompting",
        "title": "Prompt Tasarımı",
        "category": "ai-ml",
        "summary": "Prompt tasarımı, dil modelinden istenen davranışı almak için girdinin biçimlendirilmesidir. RAG'de sistem promptu, modeli yalnızca verilen bağlama dayanmaya yönlendirir.",
        "facts": [
            "Sistem promptu modelin rolünü ve kurallarını belirler.",
            "RAG'de model, bağlamda yoksa bilgi uydurmaması için açıkça yönlendirilir.",
            "Yapılandırılmış çıktı (örn. JSON), atıf ve alanların güvenilir ayrıştırılmasını sağlar.",
            "Sıcaklık (temperature) düşükse çıktı daha belirlenimci ve tutarlı olur.",
        ],
        "faq": [
            ("Halüsinasyon nasıl azaltılır?", "Modele yalnızca verilen kaynaklardan cevap vermesi ve yoksa bilmediğini söylemesi talimatı verilir."),
            ("Temperature ne işe yarar?", "Çıktının rastgeleliğini ayarlar; düşük değer daha kararlı, yüksek değer daha yaratıcı sonuç verir."),
            ("Çok turlu sohbette bağlam nasıl korunur?", "Önceki mesajlar geçmiş olarak eklenir ve takip sorusu bağımsız sorguya yeniden yazılır."),
        ],
        "steps": [
            "Rol ve kuralları içeren bir sistem promptu yazın.",
            "Kaynakları numaralandırarak bağlamı ekleyin.",
            "Modelden atıf işaretlerini kurallı biçimde isteyin.",
            "Sıcaklık ve uzunluk parametrelerini göreve göre ayarlayın.",
        ],
    },
    {
        "slug": "sse",
        "title": "Server-Sent Events (SSE)",
        "category": "ai-ml",
        "summary": "SSE, sunucudan istemciye tek yönlü, sürekli bir olay akışı sağlayan bir HTTP tekniğidir. Streaming LLM cevaplarını token token iletmek için uygundur.",
        "facts": [
            "SSE, text/event-stream içerik tipiyle çalışır ve bağlantı açık kalır.",
            "Her olay 'event:' ve 'data:' satırlarıyla, boş satırla ayrılarak gönderilir.",
            "SSE tek yönlüdür (sunucudan istemciye); iki yön gerekiyorsa WebSocket kullanılır.",
            "Ara belleklemeyi kapatmak için X-Accel-Buffering: no gibi başlıklar kullanılır.",
        ],
        "faq": [
            ("SSE ile WebSocket farkı nedir?", "SSE tek yönlü ve HTTP üzerinden basittir; WebSocket çift yönlüdür."),
            ("Token akışı nasıl iletilir?", "Her token bir 'data:' olayı olarak gönderilir; istemci akarken birleştirir."),
            ("Proxy arabelleği sorun olur mu?", "Evet; arabellekleme akışı geciktirir, bu yüzden kapatılması önerilir."),
        ],
        "steps": [
            "Yanıtı text/event-stream olarak döndürün.",
            "Olayları event/data satır formatında serileştirin.",
            "Arabellek başlıklarını akışa uygun ayarlayın.",
            "İstemcide akışı okuyup parçaları birleştirin.",
        ],
    },
    {
        "slug": "evaluation",
        "title": "RAG Değerlendirmesi",
        "category": "procedures",
        "summary": "RAG değerlendirmesi, sistemin cevap doğruluğunu ve kaynak isabetini ölçer. Golden set ve RAGAS gibi metriklerle tekrarlanabilir kıyaslama yapılır.",
        "facts": [
            "Golden set, soru ile beklenen cevap/kaynak eşlerinden oluşan referans kümesidir.",
            "RAGAS; faithfulness, answer relevancy ve context precision/recall gibi metrikler sunar.",
            "Latency ve token kullanımı, kalite yanında maliyet/performans göstergeleridir.",
            "Başarısız örneklerin analizi, chunk boyutu ve retrieval parametrelerini ayarlamaya yardım eder.",
        ],
        "faq": [
            ("Faithfulness ne ölçer?", "Cevabın getirilen bağlama sadık olup olmadığını; uydurma bilgi cezalandırılır."),
            ("Golden set neden gerekir?", "Değişikliklerin kaliteyi artırıp azalttığını tekrarlanabilir biçimde ölçmek için."),
            ("Context recall nedir?", "Beklenen bilgiyi içeren bağlamın getirilip getirilmediğini ölçer."),
        ],
        "steps": [
            "50+ soru içeren bir golden set hazırlayın.",
            "Sistemi her soru için çalıştırıp cevap ve kaynakları toplayın.",
            "Doğruluk, citation isabeti ve latency'yi ölçün.",
            "Başarısız örnekleri analiz edip parametreleri ayarlayın.",
        ],
    },
]

# --- Sözlük (kısa tanım dokümanları) -------------------------------------------

GLOSSARY: dict[str, str] = {
    "Chunk": "Bir belgeden üretilen, embedding ve indeksleme için uygun boyuttaki metin parçası.",
    "Embedding": "Metni anlamsal bir sayısal vektöre dönüştüren temsil.",
    "Dense vektör": "Çoğu boyutu dolu, anlamsal benzerliği yakalayan yoğun sayısal vektör.",
    "Sparse vektör": "Çoğu boyutu sıfır olan, sözcük tabanlı (örn. BM25) seyrek vektör.",
    "BM25": "Terim frekansı ve IDF'e dayanan klasik seyrek sıralama fonksiyonu.",
    "IDF": "Ters belge frekansı; nadir terimlere daha yüksek ağırlık veren istatistik.",
    "RRF": "Reciprocal Rank Fusion; birden çok sıralı listeyi sıra konumlarına göre birleştirir.",
    "Cosine similarity": "İki vektör arasındaki açının kosinüsü ile ölçülen benzerlik.",
    "top_k": "Bir aramada döndürülecek en yakın sonuç sayısı.",
    "Citation": "Cevabı, kaynağı olan belge parçasına bağlayan atıf.",
    "Retrieval": "Bir sorguya en ilgili belge parçalarını getirme işlemi.",
    "Hybrid search": "Dense ve sparse aramayı birleştiren getirme yöntemi.",
    "Vektör veritabanı": "Vektörleri saklayıp benzerlik araması yapan özel veritabanı.",
    "Payload": "Bir vektör noktasına iliştirilen metadata (belge adı, kategori, sayfa vb.).",
    "Collection": "Qdrant'ta noktaların saklandığı, vektör şemasıyla tanımlı grup.",
    "Upsert": "Kayıt varsa güncelleyen, yoksa ekleyen yazma işlemi.",
    "ANN": "Yaklaşık en yakın komşu; büyük ölçekte hızlı benzerlik araması.",
    "HNSW": "Grafik tabanlı, yaygın kullanılan bir ANN indeks algoritması.",
    "ACID": "Atomiklik, tutarlılık, izolasyon ve dayanıklılık işlem güvenceleri.",
    "MVCC": "Çok sürümlü eşzamanlılık denetimi; okuyucu ile yazıcıyı engellemeden ayırır.",
    "JSONB": "PostgreSQL'de indekslenebilir ikili JSON veri tipi.",
    "Pod": "Kubernetes'te bir veya çok konteyner içeren en küçük dağıtım birimi.",
    "Deployment": "Pod kopyalarını yöneten ve güncelleyen Kubernetes nesnesi.",
    "Service (K8s)": "Pod'lara kararlı adres ve yük dengeleme sağlayan Kubernetes nesnesi.",
    "Ingress": "Kümeye HTTP trafiğini yönlendiren Kubernetes kaynağı.",
    "Volume": "Konteyner yaşam döngüsünden bağımsız kalıcı depolama.",
    "Dockerfile": "Bir imajın nasıl kurulacağını tanımlayan talimat dosyası.",
    "Multi-stage build": "Derleme ve çalıştırma aşamalarını ayırarak imaj boyutunu küçülten teknik.",
    "ASGI": "Async Python web uygulamaları için sunucu-uygulama arayüzü.",
    "Uvicorn": "FastAPI için yaygın kullanılan bir ASGI sunucusu.",
    "Depends": "FastAPI'de bağımlılık enjeksiyonu mekanizması.",
    "Pydantic model": "Tip ipuçlarıyla veri doğrulayan sınıf.",
    "Counter (metrik)": "Yalnızca artan Prometheus metrik tipi.",
    "Gauge": "Artıp azalabilen Prometheus metrik tipi.",
    "Histogram": "Değer dağılımını kovalara göre toplayan Prometheus metrik tipi.",
    "PromQL": "Prometheus zaman serisi sorgu dili.",
    "Temperature": "LLM çıktısının rastgeleliğini ayarlayan parametre.",
    "System prompt": "Modelin rolünü ve kurallarını belirleyen yönerge.",
    "Query rewriting": "Takip sorusunu, geçmişe göre bağımsız bir sorguya dönüştürme.",
    "Conversation memory": "Çok turlu sohbette önceki mesajları bağlam olarak tutma.",
    "Faithfulness": "Cevabın getirilen bağlama sadakatini ölçen RAG metriği.",
    "Context precision": "Getirilen bağlamın ne kadarının ilgili olduğunu ölçen metrik.",
    "Context recall": "Beklenen bilginin bağlamda getirilip getirilmediğini ölçen metrik.",
    "Golden set": "Soru ile beklenen cevap/kaynak eşlerinden oluşan referans kümesi.",
    "Latency": "Bir isteğin tamamlanması için geçen süre.",
    "Token": "Modelin metni işlediği en küçük birim.",
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def build(out_dir: Path) -> int:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    count = 0

    for t in TOPICS:
        cat = t["category"]
        base = out_dir / cat

        facts = "\n".join(f"- {f}" for f in t["facts"])
        overview = f"# {t['title']} — Genel Bakış\n\n{t['summary']}\n\n## Temel Bilgiler\n\n{facts}"
        _write(base / f"{t['slug']}-overview.md", overview)
        count += 1

        faq_body = "\n\n".join(f"**S: {q}**\n\nC: {a}" for q, a in t["faq"])
        faq = f"# {t['title']} — Sık Sorulan Sorular\n\n{faq_body}"
        _write(base / f"{t['slug']}-faq.md", faq)
        count += 1

        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(t["steps"], 1))
        howto = f"# {t['title']} — Nasıl Yapılır\n\n{t['title']} ile çalışmaya başlamak için adımlar:\n\n{steps}"
        _write(base / f"{t['slug']}-howto.md", howto)
        count += 1

    for term, definition in GLOSSARY.items():
        slug = (
            term.lower()
            .replace(" ", "-")
            .replace("(", "")
            .replace(")", "")
            .replace("ç", "c").replace("ğ", "g").replace("ı", "i")
            .replace("ö", "o").replace("ş", "s").replace("ü", "u")
        )
        doc = f"# Sözlük: {term}\n\n{term}: {definition}"
        _write(out_dir / "glossary" / f"{slug}.md", doc)
        count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Bilgi tabanı korpusunu üretir.")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "data" / "corpus"),
        help="Çıktı dizini (varsayılan: backend/data/corpus)",
    )
    args = parser.parse_args()
    out = Path(args.out)
    total = build(out)
    print(f"Korpus üretildi: {total} doküman → {out}")


if __name__ == "__main__":
    main()
