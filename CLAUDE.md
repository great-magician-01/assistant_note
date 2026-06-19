# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

智能笔记 (AI Note) — a cloud note-taking application with AI assistance powered by DeepSeek. The backend is substantially built out; the frontend is a stripped-down Vue 3 scaffold with dependencies installed but not yet wired.

- **Backend**: Python FastAPI — full auth (JWT + bcrypt), CRUD for categories (tree) and notes, Chinese full-text search via jieba + PostgreSQL tsvector
- **Frontend**: Vue 3 + Vite + TypeScript — Tailwind v4 integrated, dependencies installed, but `main.ts` only mounts an empty App
- **Database**: PostgreSQL (primary) + SQLite (cache)
- **AI**: Multi-model — model pool (`ai_models`) and runtime configs (`ai_configs`) stored in the DB and managed via API (no `.env` AI config). Different models (OpenAI/Anthropic format, multimodal, etc.) can be configured per use case. A tool registry (`apps/ai/tools/`) exposes callable tools (note search, tag search) that configs can enable.
- **Roles**: Users have a role (`user`/`admin`) via a `roles` lookup table. An admin account is bootstrapped from `.env` on startup (created if missing, else password reset + forced admin). AI config/tool management is admin-only.

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
| `apps/api/` | API endpoint definitions (route handlers) — `auth.py`, `category.py`, `note.py`, `upload.py`, `ai_model.py`, `ai_config.py`, `ai_tool.py` |
| `apps/model/` | SQLAlchemy ORM models (PostgreSQL) — `base.py`, `user.py`, `category.py`, `note.py`, `role.py`, `ai_model.py`, `ai_config.py` |
| `apps/router/` | Route registration — `api_router.py` aggregates sub-routers under `/api` |
| `apps/service/` | Business logic layer — `auth_service.py`, `category_service.py`, `note_service.py`, `ai_model_service.py`, `ai_config_service.py` |
| `apps/ai/tools/` | AI tool registry — `base.py` (BaseTool), `registry.py`, built-in tools (`search_notes`, `search_notes_by_tag`) |
| `apps/utils/config.py` | Configuration loading from `.env` via pydantic-settings |
| `apps/utils/database.py` | Async SQLAlchemy engine, session factory, and `get_db` FastAPI dependency |
| `apps/utils/security.py` | JWT creation/validation, bcrypt password hashing, `get_current_user` + `get_current_admin` dependencies |
| `apps/utils/snowflake.py` | Thread-safe 64-bit Snowflake ID generator (epoch: 2024-01-01) |
| `apps/utils/logger.py` | Date+size rotating file logger with trace-id injection via ContextVar |
| `apps/utils/exceptions.py` | `BusinessError` (→400), `NotFoundError` (→404), `ForbiddenError` (→403) exception classes |
| `apps/utils/cache.py` | Caching utilities (stub — not yet implemented) |

#### API Routes

All routes are prefixed with `/api` and require `Authorization: Bearer <token>` (except auth endpoints). **All endpoints use only `GET` and `POST` — no `PUT`/`DELETE`** (see design decisions below). Updates use `POST /{id}/update`, deletes use `POST /{id}/delete`.

| Prefix | Tag | Endpoints |
|---|---|---|
| `/v1/auth` | Auth | `POST /register`, `POST /login`, `POST /refresh`, `GET /me` |
| `/v1/category` | Category | `GET /` (tree), `POST /`, `POST /{id}/update`, `POST /{id}/delete` |
| `/v1/note` | Note | `GET /` (paginated + search + tag filter), `GET /tags`, `POST /move`, `GET /{id}`, `POST /`, `POST /{id}/update`, `POST /{id}/delete` |
| `/v1/ai-model` | AiModel | `GET /` (pool list; non-admin sees `api_key` masked), `POST /` (admin), `POST /{id}/update` (admin), `POST /{id}/delete` (admin) |
| `/v1/ai-config` | AiConfig | `GET /` (config list, all users; no `api_key` exposed), `POST /` (admin), `POST /{id}/update` (admin), `POST /{id}/delete` (admin) |
| `/v1/ai-tool` | AiTool | `GET /` (tool registry metadata; admin only) |
| `/v1/upload` | Upload | `POST /image` (image upload; authenticated, returns public `url`) |
| `/uploads` | Static | public StaticFiles mount serving uploaded images (no auth) |
| `/health` | Health | `GET /` (no auth) |

#### Key Backend Design Decisions

- **Snowflake IDs**: All primary keys are 64-bit Snowflake IDs generated in the application layer (not auto-increment). Global singleton with `machine_id=1`.
- **Timestamps**: `created_at`/`updated_at` use application-server `datetime.now()` via the `TimestampMixin`, NOT database `now()`. This was an intentional refactor (commit `0ab4858`).
- **Soft delete**: Categories and notes use `is_deleted` flag (0=正常, 1=已删除). All queries filter `is_deleted == 0`. Category deletion cascades to descendants.
- **Category name uniqueness**: Enforced via a **partial unique index** `uq_category_user_name_parent` on `(user_id, category_name, parent_id) WHERE is_deleted = 0` (migration 002). The original plain `UNIQUE` constraint counted soft-deleted rows, blocking same-name recreation after delete. The app-layer duplicate check still uses `is_deleted == 0` and `IS NULL` for `parent_id`, so it guards top-level (NULL parent) duplicates that the DB index treats as distinct across NULLs.
- **Category deletion guard**: `delete_category` refuses to delete if any non-deleted note exists under the category or its descendants — otherwise those notes would be orphaned (pointing at a soft-deleted category). The user must move/delete the notes first (returns `BusinessError`). Empty child categories are still cascade-soft-deleted.
- **Note tags**: `note_tags` is a JSONB array, indexed with a GIN index `ix_notes_note_tags` (migration 002). `GET /v1/note/?tag=...` filters via JSONB containment (`@>`); `GET /v1/note/tags` returns all distinct tags for the user.
- **Chinese full-text search**: PostgreSQL's built-in parsers don't tokenize Chinese. The app uses **jieba** to segment title/content before feeding to `to_tsvector('simple', ...)`, and segments the search keyword for `plainto_tsquery`. No PostgreSQL extensions (zhparser/pg_jieba) needed. Title gets weight 'A', content gets weight 'B'. A GIN index exists on `search_vector`.
- **Sliding token refresh**: Every authenticated request gets a fresh access token in the `X-Access-Token` response header (set by middleware in `main.py`, token generated in `get_current_user` dependency). This resets the 2-hour expiry window on each request.
- **Trace ID**: Every request gets a `trace_id` (UUID hex, 16 chars) injected into all log records via `ContextVar` + logging Filter. Also returned in `X-Trace-Id` response header.
- **Log rotation**: Custom `_DateSizeRotatingFileHandler` — one directory per day (`{LOG_DIR}/YYYY-MM-DD/`), files roll at 200 MB. Thread-safe via `threading.Lock`.
- **Password hashing**: Uses `bcrypt` directly (not passlib) due to compatibility issues with bcrypt 5.x.
- **No foreign keys**: Database has no FK constraints — relationships are enforced in the application layer. (See migration SQL.)
- **AI multi-model config (DB-backed)**: AI provider config moved out of `.env` into two global tables: `ai_models` (pool of connection entries) and `ai_configs` (a pool model + runtime params: prompt, tools, json_output, temperature...). Both are **global/shared** (no `user_id`) — an exception to the per-user isolation used elsewhere. `api_key` is stored plaintext. Deleting a pool model is blocked while a config references it. `ai_configs.is_default` is kept to a single global row via a partial unique index.
- **Roles & admin**: `roles` is a system lookup table seeded with fixed IDs (`1`=user, `2`=admin); `users.role_id` references it (no FK, default `1`). Constants in `apps/model/role.py` (`ROLE_ID_USER`/`ROLE_ID_ADMIN`) are used directly on the hot path (e.g. the admin guard) instead of querying. An admin account is bootstrapped from `.env` (`ADMIN_ACCOUNT`/`ADMIN_PASSWORD`) on startup via `auth_service.ensure_admin_account`: created if missing, else password reset + role forced to admin (password resets every start by design). The bootstrap runs in `lifespan` and tolerates DB errors so the app still boots.
- **Admin-only endpoints**: `get_current_admin` (in `security.py`) wraps `get_current_user` and raises `ForbiddenError` (→403) if `user.role_id != ROLE_ID_ADMIN`. AI config CUD (`/ai-model`, `/ai-config` POST/update/delete) and the tool list (`/ai-tool GET`) require admin. AI config `GET` is open to all authenticated users; `/ai-model GET` masks `api_key` for non-admins (`sk-***d112`), and `/ai-config GET` never exposes `api_key`. `ForbiddenError` (403) is registered in `main.py` alongside `BusinessError`(400)/`NotFoundError`(404).
- **AI tool registry**: `apps/ai/tools/` holds self-describing tools (name, description, JSON-schema `parameters`, async `execute`). `registry.py` registers them; `ai_configs.tools` stores tool names. Built-in tools: `search_notes` (full-text) and `search_notes_by_tag` (tag filter), both wrapping `note_service.list_notes` and returning trimmed note summaries (no content). `GET /v1/ai-tool` returns the metadata (admin only) so configs can pick tools. Add a tool by subclassing `BaseTool` and appending to `_TOOLS` in `registry.py`.
- **`exclude_unset` pattern**: Update endpoints use `model_dump(exclude_unset=True)` so omitted fields are left unchanged and explicit `None` means "set to NULL".
- **Image uploads**: `POST /api/v1/upload/image` (in `apps/api/upload.py`, requires `python-multipart`) accepts one image, validates extension whitelist + size cap (`UPLOAD_ALLOWED_EXT`/`UPLOAD_MAX_SIZE_MB` from `.env`), and stores it at `<UPLOAD_DIR>/<user_id>/<snowflake>.<ext>`. The Snowflake filename makes URLs non-enumerable; files are served **publicly** via a `StaticFiles` mount at `UPLOAD_BASE_URL` (`/uploads`) in `main.py` (mounted with `check_dir=False` — the dir is created in `lifespan`). No DB table tracks uploads; image URLs live as Markdown `![](url)` inside `note_content`. No orphan cleanup yet. The frontend wires Vditor's custom `upload.handler` (in `NoteEditor.vue`) to the axios-based `uploadImage` so the same path covers toolbar pick, paste, and drag-and-drop while keeping the auth token fresh.
- **Move notes**: `POST /v1/note/move` accepts `note_ids: list[int]` + `category_id` (single note = list of one; `category_id=null` → uncategorized). Validates the target category exists/belongs to user and every note exists/owned; returns `{moved, total, category_id}`. Only notes whose category actually changed are counted in `moved`.
- **GET/POST only**: Every API endpoint uses only `GET` (read) and `POST` (write/action) — no `PUT` or `DELETE`. Updates are `POST /{id}/update`, deletions are `POST /{id}/delete`. This is a project-wide convention; apply it to all future endpoints.
- **IDs as strings**: Snowflake IDs are 64-bit and exceed JavaScript's `Number.MAX_SAFE_INTEGER` (2^53), so they MUST be serialized as JSON strings. All `*_id` fields in request/response models use the `SnowflakeId` / `OptionalSnowflakeId` annotated types (`apps/utils/types.py`), which coerce `int`↔`str` at the API boundary. The service/ORM layers keep IDs as `int`; conversion happens in the API handlers (path params parsed with `int()`, body fields coerced before calling services). Path params like `{note_id}`/`{category_id}` are declared `str` and converted to `int` inside the handler.

#### Database Models

- **User** (`users`): `user_id`, `user_account` (unique), `user_name`, `user_password` (bcrypt), `role_id` (default `1`=普通用户, references `roles`, no FK), `is_active`
- **Role** (`roles`) — system lookup table seeded with fixed IDs (migration 004): `role_id` (`1`=普通用户, `2`=管理员), `role_code` (unique, `user`/`admin`), `role_name`, `remark`. App code references the IDs via constants in `apps/model/role.py` (`ROLE_ID_USER`/`ROLE_ID_ADMIN`) instead of querying.
- **Category** (`categories`): `category_id`, `user_id`, `category_name`, `category_icon`, `category_sort`, `parent_id` (nullable, self-referential for tree), `is_deleted`. Partial unique index on `(user_id, category_name, parent_id) WHERE is_deleted = 0`.
- **Note** (`notes`): `note_id`, `user_id`, `category_id`, `note_title`, `note_content` (Markdown), `note_summary` (AI-generated), `note_tags` (JSONB array), `search_vector` (TSVECTOR, deferred), `is_pinned`, `is_deleted`, `note_word_count`. Composite index on `(user_id, is_deleted, updated_at)`; GIN index on `search_vector`; GIN index on `note_tags`.
- **AiModel** (`ai_models`) — global model pool (no `user_id`): `model_id`, `name`, `api_format` (openai/anthropic), `base_url`, `api_key` (plaintext), `model`, `is_multimodal`, `max_tokens`, `remark`, `extra_config` (JSONB), `is_active`, `is_deleted`. Migration 003.
- **AiConfig** (`ai_configs`) — global runtime config (no `user_id`): `config_id`, `config_name`, `model_id` (references pool, app-layer validated, no FK), `system_prompt`, `tools` (JSONB array of tool names), `json_output`, `temperature`, `top_p`, `max_tokens` (nullable override), `is_default`, `is_active`, `is_deleted`. Partial unique index `uq_ai_configs_default` keeps at most one default globally (`WHERE is_default = 1 AND is_deleted = 0`). Migration 003.

Key dependencies: FastAPI 0.137, SQLAlchemy 2.0 (async with asyncpg), Pydantic v2, PyJWT 2.13, bcrypt 5.0, jieba 0.42, OpenAI SDK 2.41, python-multipart 0.0.32 (file uploads), Uvicorn 0.49.

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
- `ADMIN_ACCOUNT` / `ADMIN_PASSWORD` — bootstrap admin account; on startup the account is created if missing (with the admin role) or, if it exists, its password is reset and role forced to admin. Leave empty to skip.
- `UPLOAD_DIR` / `UPLOAD_BASE_URL` / `UPLOAD_MAX_SIZE_MB` / `UPLOAD_ALLOWED_EXT` — image upload storage dir (default `uploads`), public URL prefix (default `/uploads`, mounted as StaticFiles), per-file size cap (default 10), and comma-separated extension whitelist (default `png,jpg,jpeg,gif,webp`; SVG excluded by default since it runs `<script>` when the public URL is opened directly).

(AI provider config is no longer in `.env` — it lives in the `ai_models`/`ai_configs` tables, managed via API.)

### Database

PostgreSQL is the primary database. Migrations are raw SQL files in `migration/` (**no Alembic**): `001_init_tables.sql` (users/categories/notes + FTS GIN index), `002_partial_unique_and_tags_index.sql` (category partial unique index + note_tags GIN), `003_ai_model_and_config.sql` (ai_models + ai_configs), `004_roles_and_user_role.sql` (roles + users.role_id). No FK constraints by design.

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
