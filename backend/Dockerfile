FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Bağımlılıklar kaynak koddan önce kurulur; kod değiştiğinde katman önbelleği
# korunur ve `uv sync` yeniden çalışmaz.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Uygulama root olarak çalışmamalı; olası bir açıkta hasar yüzeyini sınırlar.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
