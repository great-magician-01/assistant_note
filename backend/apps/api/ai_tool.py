"""AI tool registry API endpoints — /v1/ai-tool/"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.apps.ai.tools import list_tool_metadata
from backend.apps.model.user import User
from backend.apps.utils.security import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ai-tool", tags=["AiTool"])


# ── Response schemas ─────────────────────────────────────────────────────────


class ToolResponse(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ToolResponse], summary="获取可用工具列表(管理员)")
async def list_tools(
    admin: User = Depends(get_current_admin),
):
    """Return metadata for every registered tool. Admin only.

    The returned ``name`` values are what ``ai_configs.tools`` stores.
    """
    logger.debug("GET /ai-tool: admin_id=%s", admin.user_id)
    return list_tool_metadata()
