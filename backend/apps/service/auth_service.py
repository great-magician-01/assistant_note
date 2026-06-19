"""Authentication business logic: register, login, refresh."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.role import ROLE_ID_ADMIN
from backend.apps.model.user import User
from backend.apps.utils.exceptions import BusinessError
from backend.apps.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)


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
    logger.debug("Register attempt: account=%s, name=%s", user_account, user_name)
    result = await db.execute(
        select(User).where(User.user_account == user_account)
    )
    if result.scalar_one_or_none() is not None:
        logger.warning("Register failed: account=%s already exists", user_account)
        raise BusinessError("账号已存在")

    user = User(
        user_account=user_account,
        user_name=user_name,
        user_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    logger.info("Register success: user_id=%s, account=%s", user.user_id, user_account)
    return _build_token_payload(user)


async def login(
    db: AsyncSession,
    user_account: str,
    password: str,
) -> dict:
    """Authenticate a user and return token payload.

    Raises BusinessError on invalid credentials or disabled account.
    """
    logger.debug("Login attempt: account=%s", user_account)
    result = await db.execute(
        select(User).where(User.user_account == user_account)
    )
    user = result.scalar_one_or_none()

    if user is None or user.is_active != 1:
        logger.warning("Login failed: account=%s not found or inactive", user_account)
        raise BusinessError("账号不存在或已禁用")

    if not verify_password(password, user.user_password):
        logger.warning("Login failed: wrong password for account=%s", user_account)
        raise BusinessError("密码错误")

    logger.info("Login success: user_id=%s, account=%s", user.user_id, user_account)
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
        logger.warning("Refresh failed: invalid or expired refresh token")
        raise BusinessError("Refresh token 无效或已过期")

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.is_active != 1:
        logger.warning("Refresh failed: user_id=%s not found or inactive", user_id)
        raise BusinessError("用户不存在或已禁用")

    logger.info("Refresh success: user_id=%s", user_id)
    return _build_token_payload(user)


async def ensure_admin_account(
    db: AsyncSession,
    account: str,
    password: str,
) -> None:
    """Ensure the bootstrap admin account exists and is an admin.

    Called on startup. If the account does not exist it is created with the
    admin role; if it exists, its role is forced to admin and its password is
    reset to the configured value (per design: password is reset every start).
    No-op when account/password are empty.
    """
    if not account or not password:
        logger.warning("Admin bootstrap skipped: ADMIN_ACCOUNT/ADMIN_PASSWORD not set")
        return

    result = await db.execute(select(User).where(User.user_account == account))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            user_account=account,
            user_name="管理员",
            user_password=hash_password(password),
            role_id=ROLE_ID_ADMIN,
        )
        db.add(user)
        logger.info("Admin bootstrap: created admin account=%s", account)
    else:
        user.role_id = ROLE_ID_ADMIN
        user.user_password = hash_password(password)
        if user.is_active != 1:
            user.is_active = 1
        logger.info("Admin bootstrap: ensured admin role + reset password for account=%s", account)

    await db.flush()
