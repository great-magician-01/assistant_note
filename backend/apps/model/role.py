"""Role ORM model + role constants.

Roles is a small system-level lookup table seeded by migration 004 with fixed
IDs, so the app can reference them by constant without a DB lookup on the hot
path (e.g. the admin guard).
"""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.utils.snowflake import snowflake_id

# Role codes
ROLE_USER = "user"
ROLE_ADMIN = "admin"

# Seeded role IDs (migration 004). Reference these directly instead of querying.
ROLE_ID_USER = 1
ROLE_ID_ADMIN = 2


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="角色ID",
    )
    role_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        comment="角色编码(user/admin)",
    )
    role_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="角色名称",
    )
    remark: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="备注",
    )
