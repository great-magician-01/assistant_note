"""User ORM model."""

from sqlalchemy import BigInteger, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
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
    is_active: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="是否启用(0-禁用 1-启用)",
    )
