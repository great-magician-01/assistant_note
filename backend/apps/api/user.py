"""User management API endpoints — /v1/user/

Admin-only: list users and act on registrations (approve / reject) and
accounts (enable/disable, reset password). All endpoints use GET/POST per
project convention.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.service import user_service
from backend.apps.utils.database import get_db
from backend.apps.utils.security import get_current_admin
from backend.apps.utils.types import SnowflakeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/user", tags=["User"])


# ── Request / Response schemas ───────────────────────────────────────────────


class UserResponse(BaseModel):
    user_id: SnowflakeId
    user_account: str
    user_name: str
    role_id: SnowflakeId
    role_code: str | None = None
    role_name: str | None = None
    is_active: int
    audit_status: int
    created_at: str | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class UserUpdateRequest(BaseModel):
    is_active: Optional[int] = Field(None, description="是否启用(0-禁用 1-启用)")


class ResetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=128, description="新密码")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=UserListResponse, summary="用户列表(管理员)")
async def list_users(
    status: Optional[int] = Query(None, description="审核状态过滤(0=待审核 1=已通过 2=已拒绝)"),
    keyword: Optional[str] = Query(None, description="账号/用户名模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("GET /user: admin_id=%s, status=%s, keyword=%r", admin.user_id, status, keyword)
    return await user_service.list_users(
        db, status=status, keyword=keyword, page=page, page_size=page_size
    )


@router.post("/{user_id}/approve", response_model=UserResponse, summary="审核通过(管理员)")
async def approve_user(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    uid = int(user_id)
    logger.debug("POST /user/%s/approve: admin_id=%s", uid, admin.user_id)
    return await user_service.approve_user(db, user_id=uid)


@router.post("/{user_id}/reject", response_model=UserResponse, summary="审核拒绝(管理员)")
async def reject_user(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    uid = int(user_id)
    logger.debug("POST /user/%s/reject: admin_id=%s", uid, admin.user_id)
    return await user_service.reject_user(db, user_id=uid, admin_id=admin.user_id)


@router.post("/{user_id}/update", response_model=UserResponse, summary="更新用户(管理员)")
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    uid = int(user_id)
    fields = body.model_dump(exclude_unset=True)
    logger.debug("POST /user/%s/update: admin_id=%s, fields=%s", uid, admin.user_id, list(fields.keys()))
    return await user_service.update_user(db, user_id=uid, fields=fields, admin_id=admin.user_id)


@router.post("/{user_id}/reset-password", summary="重置密码(管理员)")
async def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    uid = int(user_id)
    logger.debug("POST /user/%s/reset-password: admin_id=%s", uid, admin.user_id)
    await user_service.reset_password(db, user_id=uid, password=body.password)
    return {"message": "密码已重置"}
