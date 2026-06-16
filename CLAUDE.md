# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

智能笔记 (AI Note) — a cloud note-taking application with AI assistance powered by DeepSeek. The backend is substantially built out; the frontend is a stripped-down Vue 3 scaffold with dependencies installed but not yet wired.

- **Backend**: Python FastAPI — full auth (JWT + bcrypt), CRUD for categories (tree) and notes, Chinese full-text search via jieba + PostgreSQL tsvector
- **Frontend**: Vue 3 + Vite + TypeScript — Tailwind v4 integrated, dependencies installed, but `main.ts` only mounts an empty App
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

# Run backend dev server
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

### VS Code Debugging

`.vscode/launch.json` has two debugpy configurations for the FastAPI backend (with and without hot reload), using the `.venv` Python interpreter on port 6581.

## Architecture

### Backend (`backend/`)

Modular FastAPI application with this layered structure:

| Directory | Purpose |
|---|---|
| `main.py` | FastAPI app entry point — CORS, middleware, exception handlers, lifespan |
| `apps/api/` | API endpoint definitions (route handlers) — `auth.py`, `category.py`, `note.py` |
| `apps/model/` | SQLAlchemy ORM models (PostgreSQL) — `base.py`, `user.py`, `category.py`, `note.py` |
| `apps/router/` | Route registration — `api_router.py` aggregates sub-routers under `/api` |
| `apps/service/` | Business logic layer — `auth_service.py`, `category_service.py`, `note_service.py` |
| `apps/utils/config.py` | Configuration loading from `.env` via pydantic-settings |
| `apps/utils/database.py` | Async SQLAlchemy engine, session factory, and `get_db` FastAPI dependency |
| `apps/utils/security.py` | JWT creation/validation, bcrypt password hashing, `get_current_user` dependency |
| `apps/utils/snowflake.py` | Thread-safe 64-bit Snowflake ID generator (epoch: 2024-01-01) |
| `apps/utils/logger.py` | Date+size rotating file logger with trace-id injection via ContextVar |
| `apps/utils/exceptions.py` | `BusinessError` (→400) and `NotFoundError` (→404) exception classes |
| `apps/utils/cache.py` | Caching utilities (stub — not yet implemented) |

#### API Routes

All routes are prefixed with `/api` and require `Authorization: Bearer <token>` (except auth endpoints).

| Prefix | Tag | Endpoints |
|---|---|---|
| `/auth/v1` | Auth | `POST /register`, `POST /login`, `POST /refresh`, `GET /me` |
| `/category/v1` | Category | `GET /` (tree), `POST /`, `PUT /{id}`, `DELETE /{id}` |
| `/note/v1` | Note | `GET /` (paginated + search), `GET /{id}`, `POST /`, `PUT /{id}`, `DELETE /{id}` |
| `/health` | Health | `GET /` (no auth) |

#### Key Backend Design Decisions

- **Snowflake IDs**: All primary keys are 64-bit Snowflake IDs generated in the application layer (not auto-increment). Global singleton with `machine_id=1`.
- **Timestamps**: `created_at`/`updated_at` use application-server `datetime.now()` via the `TimestampMixin`, NOT database `now()`. This was an intentional refactor (commit `0ab4858`).
- **Soft delete**: Categories and notes use `is_deleted` flag (0=正常, 1=已删除). All queries filter `is_deleted == 0`. Category deletion cascades to descendants.
- **Chinese full-text search**: PostgreSQL's built-in parsers don't tokenize Chinese. The app uses **jieba** to segment title/content before feeding to `to_tsvector('simple', ...)`, and segments the search keyword for `plainto_tsquery`. No PostgreSQL extensions (zhparser/pg_jieba) needed. Title gets weight 'A', content gets weight 'B'. A GIN index exists on `search_vector`.
- **Sliding token refresh**: Every authenticated request gets a fresh access token in the `X-Access-Token` response header (set by middleware in `main.py`, token generated in `get_current_user` dependency). This resets the 2-hour expiry window on each request.
- **Trace ID**: Every request gets a `trace_id` (UUID hex, 16 chars) injected into all log records via `ContextVar` + logging Filter. Also returned in `X-Trace-Id` response header.
- **Log rotation**: Custom `_DateSizeRotatingFileHandler` — one directory per day (`{LOG_DIR}/YYYY-MM-DD/`), files roll at 200 MB. Thread-safe via `threading.Lock`.
- **Password hashing**: Uses `bcrypt` directly (not passlib) due to compatibility issues with bcrypt 5.x.
- **No foreign keys**: Database has no FK constraints — relationships are enforced in the application layer. (See migration SQL.)
- **`exclude_unset` pattern**: Update endpoints use `model_dump(exclude_unset=True)` so omitted fields are left unchanged and explicit `None` means "set to NULL".

#### Database Models

- **User** (`users`): `user_id`, `user_account` (unique), `user_name`, `user_password` (bcrypt), `is_active`
- **Category** (`categories`): `category_id`, `user_id`, `category_name`, `category_icon`, `category_sort`, `parent_id` (nullable, self-referential for tree), `is_deleted`. Unique constraint on `(user_id, category_name, parent_id)`.
- **Note** (`notes`): `note_id`, `user_id`, `category_id`, `note_title`, `note_content` (Markdown), `note_summary` (AI-generated), `note_tags` (JSONB), `search_vector` (TSVECTOR, deferred), `is_pinned`, `is_deleted`, `note_word_count`. Composite index on `(user_id, is_deleted, updated_at)`.

Key dependencies: FastAPI 0.137, SQLAlchemy 2.0 (async with asyncpg), Pydantic v2, PyJWT 2.13, bcrypt 5.0, jieba 0.42, OpenAI SDK 2.41, Uvicorn 0.49.

### Frontend (`frontend/src/`)

Vue 3 SPA with Tailwind CSS v4. **Not yet wired together** — `main.ts` only imports `createApp`, `style.css`, and `App.vue`. `App.vue` is an empty component.

Dependencies installed in `package.json` but NOT imported/used yet:
- **Naive UI** — component library
- **Pinia** — state management
- **Vue Router** — routing
- **Axios** — HTTP client for backend API
- **vditor** + **highlight.js** — markdown editing with syntax highlighting
- **vuedraggable** / **sortablejs** — drag-and-drop note organization
- **VueUse** — composable utilities
- **dayjs** — date handling

`style.css` contains Tailwind v4 import and a custom theme with CSS variables (light + dark mode via `prefers-color-scheme`). The theme uses purple accent colors (`#aa3bff` / `#c084fc`).

### Configuration (`.env` / `.env.example`)

- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SCHEMA`, `DB_SSLMODE` — PostgreSQL connection (asyncpg)
- `SQLITE_PATH` — SQLite cache database path (default `./cache/sqlite.db`)
- `ACCESS_JWT_SECRET` / `REFRESH_JWT_SECRET` — JWT signing keys (HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES` (default 120) / `REFRESH_TOKEN_EXPIRE_DAYS` (default 7)
- `BACKEND_SERVER_PORT` (6581) / `FRONTEND_SERVER_PORT` (6580)
- `LOG_DIR` — log directory (default `pylogs`)
- `DEBUG` — when `true`, sets log level to DEBUG and echoes SQL queries
- `CORS_ALLOW_ORIGINS` — comma-separated or `*`
- `AI_TYPE`, `API_KEY`, `API_BASE`, `AI_MODEL` — AI provider config (for DeepSeek)

### Database

PostgreSQL is the primary database. The migration script is at `migration/001_init_tables.sql` — it creates all three tables with indexes, comments, and the GIN index for full-text search. **No Alembic** — migrations are raw SQL files. No FK constraints by design.

SQLite is referenced in config as a secondary/cache store but not yet used.

## Important Notes

- **`.env` is in `.gitignore`** — copy `.env.example` to `.env` and fill in secrets
- **No tests exist yet** — pytest is referenced in `.gitignore` but no test infrastructure is set up
- **No linting/formatting configured** — no ruff, mypy, ESLint, or Prettier configs exist
- **Virtual environment is at `.venv/`** — always activate it before running Python commands
- **No Alembic** — database migrations are raw SQL in `migration/`
- **No foreign keys in DB** — all relationships are enforced at the application layer
- **Frontend is not wired** — dependencies are installed but `main.ts`, router, store, and components are not yet set up
- **AI integration is not yet implemented** — the OpenAI SDK is installed and config fields exist, but no AI service code exists yet
