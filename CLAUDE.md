# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

智能笔记 (AI Note) — a cloud note-taking application with AI assistance powered by DeepSeek. The project is in early scaffold stage: infrastructure is set up but application code is not yet written.

- **Backend**: Python FastAPI (empty scaffold, directory structure laid out but no code)
- **Frontend**: Vue 3 + Vite + TypeScript (stripped-down scaffold, Tailwind v4 integrated)
- **Database**: PostgreSQL (primary) + SQLite (cache)
- **AI**: DeepSeek V4 Pro via OpenAI-compatible API

## Essential Commands

### Python (Backend)

All Python dependencies must use the virtual environment at `.venv/`.

```bash
# Activate virtual environment (Windows Git Bash)
source .venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt

# Add a new dependency and freeze
pip install <package> && pip freeze > requirements.txt

# Run backend dev server (once main.py is implemented)
uvicorn backend.main:app --host 0.0.0.0 --port 6581 --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (runs on port 6580)
npm run dev

# Type-check and build for production
npm run build

# Preview production build
npm run preview
```

## Architecture

### Backend (`backend/`)

Modular FastAPI application with this layered structure:

| Directory | Purpose |
|---|---|
| `main.py` | FastAPI app entry point (empty — to be created) |
| `apps/api/` | API endpoint definitions (route handlers) |
| `apps/model/` | SQLAlchemy ORM models (PostgreSQL) |
| `apps/router/` | Route registration and aggregation |
| `apps/service/` | Business logic layer |
| `apps/utils/config.py` | Configuration loading from `.env` |
| `apps/utils/cache.py` | Caching utilities |

Key dependencies: FastAPI 0.137, SQLAlchemy 2.0 (async with asyncpg), Pydantic v2, OpenAI SDK (for DeepSeek), Uvicorn.

### Frontend (`frontend/src/`)

Vue 3 SPA with Tailwind CSS v4. The tech stack is set up but **not yet wired together** — `vue-router`, `pinia`, `naive-ui`, `axios` are all in `package.json` but not imported in `main.ts` yet.

Key dependencies to be wired in:
- **Naive UI** — component library
- **Pinia** — state management
- **Vue Router** — routing
- **Axios** — HTTP client for backend API
- **vditor** + **highlight.js** — markdown editing with syntax highlighting
- **vuedraggable** / **sortablejs** — drag-and-drop note organization
- **VueUse** — composable utilities
- **dayjs** — date handling

### Configuration (`.env` / `.env.example`)

- `DB_*` — PostgreSQL connection (host, port, user, password, database, schema, sslmode)
- `SQLITE_PATH` — SQLite cache database path
- `ACCESS_JWT_SECRET` / `REFRESH_JWT_SECRET` — JWT signing keys
- `BACKEND_SERVER_PORT` / `FRONTEND_SERVER_PORT` — ports (6581 / 6580)
- `AI_TYPE` / `API_KEY` / `API_BASE` / `AI_MODEL` — AI provider config
- `CORS_ALLOW_ORIGINS` — CORS origins
- `DEBUG` — debug mode (logs SQL queries)

### Database

PostgreSQL is the primary database. No migration system is set up yet (no Alembic). SQLite is used as a secondary/cache store.

## Important Notes

- **`.env` is in `.gitignore`** — copy `.env.example` to `.env` and fill in secrets
- **No tests exist yet** — pytest is referenced in `.gitignore` but no test infrastructure is set up
- **No linting/formatting configured** — no ruff, mypy, ESLint, or Prettier configs exist
- **`backend/` Python files are all empty** — only the package `__init__.py` files exist as placeholders
- **Virtual environment is at `.venv/`** — always activate it before running Python commands
