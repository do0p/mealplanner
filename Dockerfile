# Stage 1 — build Angular (runs on the build host, never emulated)
FROM --platform=$BUILDPLATFORM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
COPY VERSION ./
RUN printf "export const APP_VERSION = '%s';\n" "$(cat VERSION)" > src/app/version.ts
RUN npm run build

# Stage 2 — Python FastAPI backend (serves both API and built frontend)
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY --from=frontend-build /backend/frontend-dist/ ./frontend-dist/

VOLUME ["/app/data"]

ENV LLM_PROVIDER=anthropic

ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV OLLAMA_MODEL=qwen3:4b
ENV OLLAMA_TIMEOUT=600
ENV OLLAMA_NUM_CTX=8192
ENV OLLAMA_CHUNK_TOKENS=2000

# ANTHROPIC_API_KEY must be passed at runtime via -e, not set here
ENV ANTHROPIC_MODEL=claude-haiku-4-5-20251001
ENV ANTHROPIC_TIMEOUT=120
ENV ANTHROPIC_CHUNK_TOKENS=5000
ENV ANTHROPIC_MAX_OUTPUT_TOKENS=16384

ENV DATA_DIR=/app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
