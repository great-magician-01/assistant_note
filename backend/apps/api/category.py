"""Category API endpoints — /v1/category/"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.service import category_service
from backend.apps.utils.database import get_db
from backend.apps.utils.security import get_current_user
from backend.apps.utils.types import OptionalSnowflakeId, SnowflakeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/category", tags=["Category"])


# ── Request / Response schemas ───────────────────────────────────────────────


class CategoryCreateRequest(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=100, description="分类名称")
    category_icon: Optional[str] = Field(None, max_length=50, description="图标标识")
    category_sort: int = Field(0, description="排序序号")
    parent_id: OptionalSnowflakeId = Field(None, description="父分类ID")


class CategoryUpdateRequest(BaseModel):
    category_name: Optional[str] = Field(None, min_length=1, max_length=100, description="分类名称")
    category_icon: Optional[str] = Field(None, max_length=50, description="图标标识")
    category_sort: Optional[int] = Field(None, description="排序序号")
    parent_id: OptionalSnowflakeId = Field(None, description="父分类ID(None=顶级分类)")


class CategoryResponse(BaseModel):
    category_id: SnowflakeId
    user_id: SnowflakeId
    category_name: str
    category_icon: Optional[str] = None
    category_sort: int
    parent_id: OptionalSnowflakeId = None
    children: list["CategoryResponse"] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[CategoryResponse], summary="获取分类列表(树形)")
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("GET /category: user_id=%s", user.user_id)
    return await category_service.list_categories(db, user.user_id)


@router.post("", response_model=CategoryResponse, summary="创建分类")
async def create_category(
    body: CategoryCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parent_id = int(body.parent_id) if body.parent_id is not None else None
    logger.debug("POST /category: user_id=%s, name=%s, parent_id=%s", user.user_id, body.category_name, parent_id)
    category = await category_service.create_category(
        db=db,
        user_id=user.user_id,
        category_name=body.category_name,
        category_icon=body.category_icon,
        category_sort=body.category_sort,
        parent_id=parent_id,
    )
    result = category_service._category_to_dict(category)
    result["children"] = []
    return result


@router.post("/{category_id}/update", response_model=CategoryResponse, summary="更新分类")
async def update_category(
    category_id: str,
    body: CategoryUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # exclude_unset: only pass fields the client actually sent, so omitting
    # parent_id leaves it unchanged instead of resetting it to NULL.
    fields = body.model_dump(exclude_unset=True)
    # Coerce string parent_id back to int for the service layer
    if "parent_id" in fields and fields["parent_id"] is not None:
        fields["parent_id"] = int(fields["parent_id"])
    cid = int(category_id)
    logger.debug("PUT /category/%s: user_id=%s, fields=%s", cid, user.user_id, list(fields.keys()))
    category = await category_service.update_category(
        db=db,
        user_id=user.user_id,
        category_id=cid,
        fields=fields,
    )
    result = category_service._category_to_dict(category)
    result["children"] = []
    return result


@router.post("/{category_id}/delete", summary="删除分类")
async def delete_category(
    category_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = int(category_id)
    logger.debug("DELETE /category/%s: user_id=%s", cid, user.user_id)
    await category_service.delete_category(db, user.user_id, cid)
    return {"message": "删除成功"}
