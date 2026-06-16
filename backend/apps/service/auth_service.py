"""Authentication business logic: register, login, refresh."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.utils.exceptions import BusinessError
from backend.apps.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)


def _build_token_payload(user: User) -> dict:
    """Build the token response payload for a user."""
    return {
        "access_token": create_access_token(user.user_id),
        "refresh_token": create_refresh_token(user.user_id),
        "user_id": user.user_id,
        "user_name": user.user_name,
        "user_account": user.user_account,
    }


async def register(
    db: AsyncSession,
    user_account: str,
    user_name: str,
    password: str,
) -> dict:
    """Register a new user and return token payload.

    Raises BusinessError if the account already exists.
    """
    result = await db.execute(
        select(User).where(User.user_account == user_account)
    )
    if result.scalar_one_or_none() is not None:
        raise BusinessError("账号已存在")

    user = User(
        user_account=user_account,
        user_name=user_name,
        user_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    return _build_token_payload(user)


async def login(
    db: AsyncSession,
    user_account: str,
    password: str,
) -> dict:
    """Authenticate a user and return token payload.

    Raises BusinessError on invalid credentials or disabled account.
    """
    result = await db.execute(
        select(User).where(User.user_account == user_account)
    )
    user = result.scalar_one_or_none()

    if user is None or user.is_active != 1:
        raise BusinessError("账号不存在或已禁用")

    if not verify_password(password, user.user_password):
        raise BusinessError("密码错误")

    return _build_token_payload(user)


async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
) -> dict:
    """Validate a refresh token and issue a new token pair.

    Raises BusinessError if the token is invalid or the user is unavailable.
    """
    payload = decode_refresh_token(refresh_token)
    if payload is None:
        raise BusinessError("Refresh token 无效或已过期")

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.is_active != 1:
        raise BusinessError("用户不存在或已禁用")

    return _build_token_payload(user)
