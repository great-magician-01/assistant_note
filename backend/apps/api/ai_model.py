"""AI model pool API endpoints — /v1/ai-model/

Access control:
  - GET (list): any authenticated user. Non-admins see api_key masked.
  - POST / {id}/update / {id}/delete: admin only.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.role import ROLE_ID_ADMIN
from backend.apps.model.user import User
from backend.apps.service import ai_model_service
from backend.apps.utils.database import get_db
from backend.apps.utils.security import get_current_admin, get_current_user
from backend.apps.utils.types import SnowflakeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ai-model", tags=["AiModel"])


def _mask_api_key(key: Optional[str]) -> Optional[str]:
    """Mask an api_key for non-admin viewers: first 3 + *** + last 4."""
    if not key:
        return key
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-4:]}"


# ── Request / Response schemas ───────────────────────────────────────────────


class AiModelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="友好显示名")
    api_format: str = Field(..., max_length=20, description="接口格式(openai/anthropic)")
    base_url: str = Field(..., max_length=500, description="API基址")
    api_key: str = Field(..., max_length=500, description="密钥")
    model: str = Field(..., min_length=1, max_length=100, description="实际模型ID")
    is_multimodal: int = Field(0, description="是否多模态(0-否 1-是)")
    max_tokens: int = Field(4096, ge=1, description="单次最大输出token")
    remark: Optional[str] = Field(None, max_length=500, description="备注")
    extra_config: Optional[dict[str, Any]] = Field(None, description="额外参数")
    is_active: int = Field(1, description="是否启用(0-禁用 1-启用)")


class AiModelUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    api_format: Optional[str] = Field(None, max_length=20)
    base_url: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = Field(None, max_length=500)
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    is_multimodal: Optional[int] = None
    max_tokens: Optional[int] = Field(None, ge=1)
    remark: Optional[str] = Field(None, max_length=500)
    extra_config: Optional[dict[str, Any]] = None
    is_active: Optional[int] = None


class AiModelResponse(BaseModel):
    model_id: SnowflakeId
    name: str
    api_format: str
    base_url: str
    api_key: str
    model: str
    is_multimodal: int
    max_tokens: int
    remark: Optional[str] = None
    extra_config: Optional[dict[str, Any]] = None
    is_active: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[AiModelResponse], summary="获取模型池列表")
async def list_ai_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the model pool. Non-admins see api_key masked."""
    logger.debug("GET /ai-model: user_id=%s", user.user_id)
    models = await ai_model_service.list_ai_models(db)
    if user.role_id != ROLE_ID_ADMIN:
        for m in models:
            m["api_key"] = _mask_api_key(m.get("api_key"))
    return models


@router.post("", response_model=AiModelResponse, summary="创建模型(管理员)")
async def create_ai_model(
    body: AiModelCreateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("POST /ai-model: admin_id=%s, name=%s", admin.user_id, body.name)
    model = await ai_model_service.create_ai_model(db=db, fields=body.model_dump())
    return ai_model_service._ai_model_to_dict(model)


@router.post("/{model_id}/update", response_model=AiModelResponse, summary="更新模型(管理员)")
async def update_ai_model(
    model_id: str,
    body: AiModelUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    fields = body.model_dump(exclude_unset=True)
    mid = int(model_id)
    logger.debug("POST /ai-model/%s/update: admin_id=%s, fields=%s", mid, admin.user_id, list(fields.keys()))
    model = await ai_model_service.update_ai_model(db=db, model_id=mid, fields=fields)
    return ai_model_service._ai_model_to_dict(model)


@router.post("/{model_id}/delete", summary="删除模型(管理员)")
async def delete_ai_model(
    model_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    mid = int(model_id)
    logger.debug("POST /ai-model/%s/delete: admin_id=%s", mid, admin.user_id)
    await ai_model_service.delete_ai_model(db=db, model_id=mid)
    return {"message": "删除成功"}
