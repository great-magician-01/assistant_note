"""API router aggregation — registers all sub-routers."""

from fastapi import APIRouter

from backend.apps.api.auth import router as auth_router
from backend.apps.api.category import router as category_router
from backend.apps.api.note import router as note_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(category_router)
api_router.include_router(note_router)
