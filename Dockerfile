FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml main.py ./
COPY agent/ ./agent/
COPY harness/ ./harness/
COPY api/ ./api/
COPY db/ ./db/
COPY data/*.json ./data/
RUN pip install --no-cache-dir .
COPY --from=web /web/dist/ ./frontend/dist/
ENV APP_DB_PATH=/app/state/app.db
EXPOSE 8888
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8888/health',timeout=3)"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8888", "--workers", "1"]
