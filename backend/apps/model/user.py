"""User ORM model."""

from sqlalchemy import BigInteger, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.model.role import ROLE_ID_USER
from backend.apps.utils.snowflake import snowflake_id


class User(Base, TimestampMixin):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="用户ID",
    )
    user_account: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        comment="账号",
    )
    user_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="用户名称",
    )
    user_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="密码(bcrypt)",
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=ROLE_ID_USER,
        server_default="1",
        index=True,
        comment="角色ID(引用roles, 默认1=普通用户)",
    )
    is_active: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="是否启用(0-禁用 1-启用)",
    )
    audit_status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="审核状态(0-待审核 1-已通过 2-已拒绝)",
    )

    __table_args__ = (
        Index("ix_users_role_id", "role_id"),
        Index("ix_users_audit_status", "audit_status"),
    )
