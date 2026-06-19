"""API router aggregation — registers all sub-routers."""

from fastapi import APIRouter

from backend.apps.api.ai_chat import router as ai_chat_router
from backend.apps.api.ai_config import router as ai_config_router
from backend.apps.api.ai_model import router as ai_model_router
from backend.apps.api.ai_tool import router as ai_tool_router
from backend.apps.api.auth import router as auth_router
from backend.apps.api.category import router as category_router
from backend.apps.api.note import router as note_router
from backend.apps.api.upload import router as upload_router
from backend.apps.api.user import router as user_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(category_router)
api_router.include_router(note_router)
api_router.include_router(upload_router)
api_router.include_router(user_router)
api_router.include_router(ai_model_router)
api_router.include_router(ai_config_router)
api_router.include_router(ai_tool_router)
api_router.include_router(ai_chat_router)
