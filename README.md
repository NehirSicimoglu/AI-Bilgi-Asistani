# AI Knowledge Assistant

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-vector%20store-DC244C?logo=qdrant&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/tests-139%20passing-brightgreen)

FastAPI ve React kullanılarak geliştirilmiş, yüklenen dokümanlar üzerinden kaynak atıflı soru-cevap üretebilen bir RAG (Retrieval-Augmented Generation) uygulaması.

Uygulamanın temel amacı, PDF/DOCX/XLSX/TXT/Markdown gibi belgeleri tek bir bilgi tabanında birleştirip, dense (embedding) ve BM25 (sparse) aramayı birlikte kullanarak sorulara ilgili kaynaklara referans veren cevaplar üretmek. Docker Compose sayesinde gerekli servisler (backend, frontend, PostgreSQL, Qdrant) tek komutla çalıştırılabiliyor.

---

**Sohbet ekranı** — bilgi tabanındaki dokümanlarla ilgili sorular sorulup kaynak atıflı cevaplar alınan ana ekran. Soldaki menüden yeni sohbet başlatılır, geçmiş sohbetlerde arama yapılır, konuşmalar projeler altında gruplanır ve son sohbetlere hızlıca erişilir.

<img width="1916" height="933" alt="proje resim2" src="https://github.com/user-attachments/assets/513cc7fc-15f9-4078-9971-d5cff764d5fe" />


---

## Özellikler

- Doküman yükleme ve otomatik parçalama (chunking) — PDF, DOCX, XLSX, TXT, Markdown desteği
- Hibrit arama: dense (embedding) + BM25 (sparse) sonuçlarının birleştirilmesi
- Çapraz-belge sorularda soruyu alt-sorgulara bölüp sonuçları birleştiren query decomposition
- LLM cevaplarının kullanılan doküman parçalarına (chunk) atıf vermesi
- Projeler bazında organize edilebilen, çok turlu konuşma geçmişi
- MCP Server üzerinden `search_documents` ve `ask_question` araçlarının MCP destekleyen dış istemcilere sunulması
- Admin paneli üzerinden sistem durumu takibi
- API anahtarı ile korunan uçlar (`X-API-Key`), `/health` ve `/metrics` hariç
- Prometheus uyumlu `/metrics` endpoint'i
- Alembic migration'ları ile sürümlenen veritabanı şeması
- Docker Compose ile tek komutla kurulum ve çalıştırma
- 139 adet birim ve entegrasyon testi

---

## Ekran Görüntüleri

**Çok turlu sohbet geçmişi** — sorulan sorular ve projeler bazında gruplanan konuşmalar sol menüden takip edilebilir.

<img width="1583" height="828" alt="projeresim" src="https://github.com/user-attachments/assets/16e49c7c-b8a5-49ae-bb76-aa1c556ded2f" />


**Doküman yönetimi** — PDF/DOCX/XLSX/TXT/MD dosyaları sürükle-bırak ile yüklenir; devre dışı bırakılan dokümanlar sistemde kayıtlı kalır ama soru-cevap sırasında kaynak olarak kullanılmaz.

<img width="1919" height="929" alt="projeresim3" src="https://github.com/user-attachments/assets/5aced25b-657f-4c8a-861a-b49059f2b427" />


**Admin paneli** — doküman/chunk sayısı, aktif LLM modelleri ve canlı log akışı tek ekrandan izlenir.

<img width="1897" height="928" alt="Ekran görüntüsü 2026-09-22 211651" src="https://github.com/user-attachments/assets/2a4a249f-9517-4c67-9550-89d4a1fa2e7e" />



---

## Kullanılan Teknolojiler

**Backend**
- FastAPI
- Python
- SQLAlchemy (async)
- PostgreSQL
- Qdrant
- Google Gemini (LLM + embedding)

**Frontend**
- React
- TypeScript
- Vite
- Tailwind CSS

**Diğer**
- Docker / Docker Compose
- Alembic

---

## Testler

Backend tarafında toplam **139 test** bulunuyor. Testler; doküman ingestion, hibrit retrieval, sohbet akışı (streaming dahil), konuşma/proje yönetimi, MCP server ve API endpoint'leri gibi temel senaryoları kapsıyor.

Testlerin tamamı ağsızdır (SQLite + in-memory Qdrant + sahte LLM/embedding sağlayıcıları), bu yüzden API anahtarı olmadan da çalışır. Tek istisna `tests/integration/test_real_infra.py`: gerçek Postgres ve Qdrant konteynerlerini testcontainers ile ayağa kaldırır, Docker çalışmıyorsa otomatik atlanır.

```bash
cd backend
uv run pytest        # testler
uv run ruff check .  # lint
```

---

## Çalıştırma

**1. Ortam dosyalarını oluşturun:**

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
cp .env.example .env            # docker-compose, frontend'e anahtarı buradan geçer
```

**2. `backend/.env` içindeki `GEMINI_API_KEY` değerini doldurun.** Anahtarı [Google AI Studio](https://aistudio.google.com/apikey) üzerinden ücretsiz alabilirsiniz.

**3. API anahtarını belirleyin.** `/health` ve `/metrics` dışındaki tüm uçlar `X-API-Key` header'ı ile korunur. Rastgele bir değer üretip **üç dosyaya da aynısını** yazın:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

| Dosya | Değişken |
|---|---|
| `backend/.env` | `API_KEY` |
| `frontend/.env` | `VITE_API_KEY` |
| `.env` (kök) | `API_KEY` — docker-compose bunu frontend'e aktarır |

> `API_KEY` boş bırakılırsa backend uçları **korumasız** açılır (yalnızca bir uyarı loglanır). Bu davranış local geliştirmeyi kolaylaştırmak içindir; herkese açık bir ortama çıkarmadan önce mutlaka doldurun.

**4. Servisleri başlatın:**

```bash
docker compose up --build
```

Servisler başladıktan sonra:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000 (Swagger: `/docs`)
- Qdrant: http://localhost:6333
- PostgreSQL: `localhost:5432`

Docker olmadan çalıştırmak isterseniz backend için `uv sync` + `uv run uvicorn app.main:app --reload`, frontend için `npm install` + `npm run dev` yeterli (PostgreSQL ve Qdrant'ın ayrıca ayakta olması gerekir).

### Veritabanı şeması

Şema Alembic ile sürümlenir. Geliştirmede uygulama açılışta tabloları kendi oluşturur; gerçek bir dağıtımda migration'ı açıkça çalıştırın:

```bash
cd backend
uv run alembic upgrade head
```


