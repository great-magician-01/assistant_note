"""Auth API endpoints — /v1/auth/"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.role import Role
from backend.apps.model.user import User
from backend.apps.service import auth_service
from backend.apps.utils.database import get_db
from backend.apps.utils.security import get_current_user
from backend.apps.utils.types import SnowflakeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


# ── Request / Response schemas ───────────────────────────────────────────────


class RegisterRequest(BaseModel):
    user_account: str = Field(..., min_length=3, max_length=50, description="账号")
    user_name: str = Field(..., min_length=1, max_length=100, description="用户名称")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class LoginRequest(BaseModel):
    user_account: str = Field(..., description="账号")
    password: str = Field(..., description="密码")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: SnowflakeId
    user_name: str
    user_account: str | None = None


class RegisterResponse(BaseModel):
    user_id: SnowflakeId
    user_account: str
    user_name: str
    message: str


class UserInfoResponse(BaseModel):
    user_id: SnowflakeId
    user_account: str
    user_name: str
    is_active: int
    audit_status: int
    role_id: SnowflakeId
    role_code: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/register", response_model=RegisterResponse, summary="用户注册")
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    logger.debug("POST /register: account=%s", body.user_account)
    result = await auth_service.register(
        db=db,
        user_account=body.user_account,
        user_name=body.user_name,
        password=body.password,
    )
    return RegisterResponse(**result)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    logger.debug("POST /login: account=%s", body.user_account)
    result = await auth_service.login(
        db=db,
        user_account=body.user_account,
        password=body.password,
    )
    return TokenResponse(**result)


@router.post("/refresh", response_model=TokenResponse, summary="刷新Token")
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    logger.debug("POST /refresh")
    result = await auth_service.refresh_access_token(
        db=db,
        refresh_token=body.refresh_token,
    )
    return TokenResponse(**result)


@router.get("/me", response_model=UserInfoResponse, summary="获取当前用户信息")
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Sliding refresh is handled by the middleware in main.py
    logger.debug("GET /me: user_id=%s", user.user_id)
    role_result = await db.execute(select(Role).where(Role.role_id == user.role_id))
    role = role_result.scalar_one_or_none()
    return UserInfoResponse(
        user_id=user.user_id,
        user_account=user.user_account,
        user_name=user.user_name,
        is_active=user.is_active,
        audit_status=user.audit_status,
        role_id=user.role_id,
        role_code=role.role_code if role else None,
    )
