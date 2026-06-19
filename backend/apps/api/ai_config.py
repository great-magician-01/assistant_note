"""AI model runtime config API endpoints — /v1/ai-config/

Access control:
  - GET (list): any authenticated user (response carries no api_key).
  - POST / {id}/update / {id}/delete: admin only.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.service import ai_config_service
from backend.apps.utils.database import get_db
from backend.apps.utils.security import get_current_admin, get_current_user
from backend.apps.utils.types import SnowflakeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ai-config", tags=["AiConfig"])


# ── Request / Response schemas ───────────────────────────────────────────────


class AiConfigCreateRequest(BaseModel):
    config_name: str = Field(..., min_length=1, max_length=100, description="配置名")
    model_id: SnowflakeId = Field(..., description="引用模型池ID")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    tools: Optional[list[str]] = Field(None, description="可用工具名数组")
    json_output: int = Field(0, description="是否强制JSON输出(0-否 1-是)")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="温度(0-2)")
    top_p: Optional[float] = Field(None, ge=0, le=1, description="nucleus sampling")
    max_tokens: Optional[int] = Field(None, ge=1, description="覆盖模型池max_tokens")
    is_default: int = Field(0, description="是否默认配置(0-否 1-是)")
    is_active: int = Field(1, description="是否启用(0-禁用 1-启用)")


class AiConfigUpdateRequest(BaseModel):
    config_name: Optional[str] = Field(None, min_length=1, max_length=100)
    model_id: Optional[SnowflakeId] = None
    system_prompt: Optional[str] = None
    tools: Optional[list[str]] = None
    json_output: Optional[int] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, ge=0, le=1)
    max_tokens: Optional[int] = Field(None, ge=1)
    is_default: Optional[int] = None
    is_active: Optional[int] = None


class AiConfigResponse(BaseModel):
    config_id: SnowflakeId
    config_name: str
    model_id: SnowflakeId
    model_name: Optional[str] = None
    model: Optional[str] = None
    api_format: Optional[str] = None
    system_prompt: Optional[str] = None
    tools: Optional[list[Any]] = None
    json_output: int
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    is_default: int
    is_active: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[AiConfigResponse], summary="获取模型配置列表")
async def list_ai_configs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("GET /ai-config: user_id=%s", user.user_id)
    return await ai_config_service.list_ai_configs(db)


@router.post("", response_model=AiConfigResponse, summary="创建模型配置(管理员)")
async def create_ai_config(
    body: AiConfigCreateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    fields = body.model_dump()
    fields["model_id"] = int(fields["model_id"])
    logger.debug("POST /ai-config: admin_id=%s, name=%s", admin.user_id, body.config_name)
    config = await ai_config_service.create_ai_config(db=db, fields=fields)
    # Re-fetch enriched view (joins model info) for a consistent response.
    return await ai_config_service.get_ai_config(db, config.config_id)


@router.post("/{config_id}/update", response_model=AiConfigResponse, summary="更新模型配置(管理员)")
async def update_ai_config(
    config_id: str,
    body: AiConfigUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    fields = body.model_dump(exclude_unset=True)
    if "model_id" in fields and fields["model_id"] is not None:
        fields["model_id"] = int(fields["model_id"])
    cid = int(config_id)
    logger.debug("POST /ai-config/%s/update: admin_id=%s, fields=%s", cid, admin.user_id, list(fields.keys()))
    await ai_config_service.update_ai_config(db=db, config_id=cid, fields=fields)
    return await ai_config_service.get_ai_config(db, cid)


@router.post("/{config_id}/delete", summary="删除模型配置(管理员)")
async def delete_ai_config(
    config_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cid = int(config_id)
    logger.debug("POST /ai-config/%s/delete: admin_id=%s", cid, admin.user_id)
    await ai_config_service.delete_ai_config(db=db, config_id=cid)
    return {"message": "删除成功"}
