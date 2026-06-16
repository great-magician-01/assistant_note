"""Category API endpoints — /category/v1/"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.service import category_service
from backend.apps.utils.database import get_db
from backend.apps.utils.security import get_current_user

router = APIRouter(prefix="/category/v1", tags=["Category"])


# ── Request / Response schemas ───────────────────────────────────────────────


class CategoryCreateRequest(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=100, description="分类名称")
    category_icon: Optional[str] = Field(None, max_length=50, description="图标标识")
    category_sort: int = Field(0, description="排序序号")
    parent_id: Optional[int] = Field(None, description="父分类ID")


class CategoryUpdateRequest(BaseModel):
    category_name: Optional[str] = Field(None, min_length=1, max_length=100, description="分类名称")
    category_icon: Optional[str] = Field(None, max_length=50, description="图标标识")
    category_sort: Optional[int] = Field(None, description="排序序号")
    parent_id: Optional[int] = Field(None, description="父分类ID(None=顶级分类)")


class CategoryResponse(BaseModel):
    category_id: int
    user_id: int
    category_name: str
    category_icon: Optional[str] = None
    category_sort: int
    parent_id: Optional[int] = None
    children: list["CategoryResponse"] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[CategoryResponse], summary="获取分类列表(树形)")
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await category_service.list_categories(db, user.user_id)


@router.post("", response_model=CategoryResponse, summary="创建分类")
async def create_category(
    body: CategoryCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    category = await category_service.create_category(
        db=db,
        user_id=user.user_id,
        category_name=body.category_name,
        category_icon=body.category_icon,
        category_sort=body.category_sort,
        parent_id=body.parent_id,
    )
    result = category_service._category_to_dict(category)
    result["children"] = []
    return result


@router.put("/{category_id}", response_model=CategoryResponse, summary="更新分类")
async def update_category(
    category_id: int,
    body: CategoryUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # exclude_unset: only pass fields the client actually sent, so omitting
    # parent_id leaves it unchanged instead of resetting it to NULL.
    fields = body.model_dump(exclude_unset=True)
    category = await category_service.update_category(
        db=db,
        user_id=user.user_id,
        category_id=category_id,
        fields=fields,
    )
    result = category_service._category_to_dict(category)
    result["children"] = []
    return result


@router.delete("/{category_id}", summary="删除分类")
async def delete_category(
    category_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await category_service.delete_category(db, user.user_id, category_id)
    return {"message": "删除成功"}
