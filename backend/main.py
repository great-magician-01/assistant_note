"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.apps.router.api_router import api_router
from backend.apps.utils.config import settings
from backend.apps.utils.database import engine
from backend.apps.utils.exceptions import BusinessError, NotFoundError
from backend.apps.utils.logger import new_trace_id, setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Application starting...")
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
    """
    # Generate trace_id for this request
    trace_id = new_trace_id()
    request.state.trace_id = trace_id

    # Add trace_id to response header for client-side debugging
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id

    # Sliding refresh: attach new access token if generated
    new_token = getattr(request.state, "new_access_token", None)
    if new_token:
        response.headers["X-Access-Token"] = new_token

    return response


# ── Exception handlers ───────────────────────────────────────────────────────
# Order matters: NotFoundError is a subclass of BusinessError, so register it
# first (FastAPI dispatches to the most specific registered handler).


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    """Resource does not exist → 404."""
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError):
    """Business rule violation → 400."""
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


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
