# syntax=docker/dockerfile:1

# ───────────────────────── Stage 1: build the frontend ─────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend

# Install deps first (cached unless package files change).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Build. Vite outputs to ./dist (and copies vditor/dist into it via the
# vditorLocalAssets writeBundle hook in vite.config.ts).
COPY frontend/ ./
RUN npm run build


# ───────────────────────── Stage 2: runtime ─────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build tools for any wheel-less source builds (most deps ship manylinux
# wheels, but keep gcc as a safety net for arm64 / future deps).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt is UTF-16 LE on this repo; re-encode to UTF-8 so pip can
# parse it inside the image.
COPY requirements.txt ./
RUN python -c "p=__import__('pathlib').Path('requirements.txt'); p.write_text(p.read_text(encoding='utf-16'), encoding='utf-8')" \
    && pip install -r requirements.txt

# Application source.
COPY backend/ ./backend/
COPY migration/ ./migration/

# Built frontend from stage 1 — served by FastAPI when FRONTEND_DIST is set.
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Runtime defaults (overridable via `docker run -e ...` or compose).
ENV FRONTEND_DIST=/app/frontend/dist \
    UPLOAD_DIR=/app/uploads \
    LOG_DIR=/app/pylogs \
    SQLITE_PATH=/app/cache/sqlite.db \
    DB_SSLMODE=prefer

# Volumes for runtime data so it survives container recreation.
VOLUME ["/app/uploads", "/app/pylogs"]

RUN mkdir -p /app/uploads /app/pylogs /app/cache

EXPOSE 6581

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "6581"]
