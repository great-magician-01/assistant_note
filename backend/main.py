"""FastAPI application entry point."""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.apps.router.api_router import api_router
from backend.apps.service import auth_service
from backend.apps.utils.config import settings
from backend.apps.utils.database import AsyncSessionLocal, engine
from backend.apps.utils.exceptions import BusinessError, ForbiddenError, NotFoundError
from backend.apps.utils.logger import new_trace_id, setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Application starting...")

    # Ensure the upload directory exists so StaticFiles can mount it. Images are
    # stored per-user under <UPLOAD_DIR>/<user_id>/ by the upload endpoint.
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Bootstrap admin account (create if missing, else reset password + force
    # admin role). Tolerates DB being unavailable so the app can still boot.
    if settings.ADMIN_ACCOUNT and settings.ADMIN_PASSWORD:
        try:
            async with AsyncSessionLocal() as session:
                await auth_service.ensure_admin_account(
                    db=session,
                    account=settings.ADMIN_ACCOUNT,
                    password=settings.ADMIN_PASSWORD,
                )
                await session.commit()
        except Exception:
            logger.exception("Admin bootstrap failed; continuing startup")
    else:
        logger.warning("Admin bootstrap skipped: ADMIN_ACCOUNT/ADMIN_PASSWORD not configured")

    yield
    # Shutdown
    logger.info("Application shutting down...")
    await engine.dispose()


app = FastAPI(
    title="智能笔记 API",
    description="AI Note — cloud note-taking application with AI assistance",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Access-Token"],
)


@app.middleware("http")
async def trace_and_sliding_middleware(request: Request, call_next):
    """Combined middleware:
    1. Assign a trace_id for every request (for log correlation)
    2. Attach new access token to response header (sliding refresh)
    3. Log the request lifecycle (method, path, status, duration)
    """
    # Generate trace_id for this request
    trace_id = new_trace_id()
    request.state.trace_id = trace_id

    start = time.perf_counter()
    logger.info("Request start: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("Request error: %s %s (%.1fms)", request.method, request.url.path, duration_ms)
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    # Add trace_id to response header for client-side debugging
    response.headers["X-Trace-Id"] = trace_id

    # Sliding refresh: attach new access token if generated
    new_token = getattr(request.state, "new_access_token", None)
    if new_token:
        response.headers["X-Access-Token"] = new_token

    logger.info("Request end: %s %s -> %d (%.1fms)", request.method, request.url.path,
                response.status_code, duration_ms)
    return response


# ── Exception handlers ───────────────────────────────────────────────────────
# Order matters: NotFoundError is a subclass of BusinessError, so register it
# first (FastAPI dispatches to the most specific registered handler).


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    """Resource does not exist → 404."""
    logger.warning("NotFound %s %s: %s", request.method, request.url.path, exc.message)
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(ForbiddenError)
async def forbidden_handler(request: Request, exc: ForbiddenError):
    """Caller lacks permission → 403."""
    logger.warning("Forbidden %s %s: %s", request.method, request.url.path, exc.message)
    return JSONResponse(status_code=403, content={"detail": exc.message})


@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError):
    """Business rule violation → 400."""
    logger.warning("BusinessError %s %s: %s", request.method, request.url.path, exc.message)
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Unexpected code error → 500. Logged with full traceback + trace_id."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


# Register all API routes
app.include_router(api_router)

# Serve uploaded images as public static files. The upload endpoint stores
# files under <UPLOAD_DIR>/<user_id>/<snowflake>.<ext> and returns URLs under
# UPLOAD_BASE_URL — these two paths must match.
app.mount(
    settings.UPLOAD_BASE_URL,
    StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False),
    name="uploads",
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
