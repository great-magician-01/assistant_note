"""User management business logic (admin): list / approve / reject / update / reset password."""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.role import Role
from backend.apps.model.user import User
from backend.apps.utils.exceptions import BusinessError, NotFoundError
from backend.apps.utils.security import hash_password

logger = logging.getLogger(__name__)

# Mirror of users.audit_status (migration 009).
AUDIT_PENDING = 0
AUDIT_APPROVED = 1
AUDIT_REJECTED = 2

# Fields an admin may toggle via update_user (exclude_unset pattern).
_UPDATABLE_FIELDS = {"is_active"}


async def list_users(
    db: AsyncSession,
    status: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return a paginated user list with role info.

    ``status`` filters audit_status (None = all). ``keyword`` matches
    user_account / user_name (ILIKE). Ordered by created_at desc.
    """
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)

    conditions = []
    if status is not None:
        conditions.append(User.audit_status == status)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(or_(User.user_account.ilike(like), User.user_name.ilike(like)))

    base = select(User, Role).outerjoin(Role, Role.role_id == User.role_id)
    for cond in conditions:
        base = base.where(cond)

    total = await db.scalar(
        select(func.count(User.user_id)).select_from(User).where(*conditions)
    )
    total = int(total or 0)

    result = await db.execute(
        base.order_by(User.created_at.desc(), User.user_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    items = [_user_to_dict(user, role) for user, role in rows]
    logger.debug("List users: status=%s keyword=%r -> %d/%d", status, keyword, len(items), total)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _get_user(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("用户不存在")
    return user


async def approve_user(db: AsyncSession, user_id: int) -> dict:
    """Approve a user (pending or previously rejected) — audit_status=1, is_active=1."""
    user = await _get_user(db, user_id)
    user.audit_status = AUDIT_APPROVED
    user.is_active = 1
    await db.flush()
    logger.info("Approve user: user_id=%s", user_id)
    return await _to_dict_with_role(db, user)


async def reject_user(db: AsyncSession, user_id: int, admin_id: int) -> dict:
    """Reject a user — audit_status=2. Refuses to reject self (avoid lockout)."""
    if user_id == admin_id:
        raise BusinessError("不能拒绝自己的账号")
    user = await _get_user(db, user_id)
    user.audit_status = AUDIT_REJECTED
    await db.flush()
    logger.info("Reject user: user_id=%s by admin_id=%s", user_id, admin_id)
    return await _to_dict_with_role(db, user)


async def update_user(
    db: AsyncSession,
    user_id: int,
    fields: dict[str, Any],
    admin_id: int,
) -> dict:
    """Update allowed fields (is_active). Refuses to disable self."""
    user = await _get_user(db, user_id)

    if "is_active" in fields and fields["is_active"] != 1 and user_id == admin_id:
        raise BusinessError("不能禁用自己的账号")

    for key in _UPDATABLE_FIELDS:
        if key in fields:
            setattr(user, key, fields[key])

    await db.flush()
    logger.info("Update user: user_id=%s fields=%s", user_id, list(fields.keys()))
    return await _to_dict_with_role(db, user)


async def reset_password(db: AsyncSession, user_id: int, password: str) -> None:
    """Reset a user's password (bcrypt). Does not change audit/active state."""
    user = await _get_user(db, user_id)
    user.user_password = hash_password(password)
    await db.flush()
    logger.info("Reset password: user_id=%s", user_id)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _to_dict_with_role(db: AsyncSession, user: User) -> dict:
    role_result = await db.execute(select(Role).where(Role.role_id == user.role_id))
    role = role_result.scalar_one_or_none()
    return _user_to_dict(user, role)


def _user_to_dict(user: User, role: Optional[Role]) -> dict:
    return {
        "user_id": user.user_id,
        "user_account": user.user_account,
        "user_name": user.user_name,
        "role_id": user.role_id,
        "role_code": role.role_code if role else None,
        "role_name": role.role_name if role else None,
        "is_active": user.is_active,
        "audit_status": user.audit_status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
