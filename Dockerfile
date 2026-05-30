# Stage 1 — build Angular (runs on the build host, never emulated)
FROM --platform=$BUILDPLATFORM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2 — Python FastAPI backend (serves both API and built frontend)
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY --from=frontend-build /backend/frontend-dist/ ./frontend-dist/

VOLUME ["/app/data"]

ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV OLLAMA_MODEL=qwen2.5:32b-instruct-q4_0
ENV OLLAMA_TIMEOUT=600
ENV DATA_DIR=/app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
