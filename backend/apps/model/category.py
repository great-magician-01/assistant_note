"""Category ORM model."""

from sqlalchemy import BigInteger, Index, Integer, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.utils.snowflake import snowflake_id


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="分类ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属用户ID",
    )
    category_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="分类名称",
    )
    category_icon: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="图标标识",
    )
    category_sort: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="排序序号",
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="父分类ID(NULL为顶级分类)",
    )
    is_deleted: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否删除(0-正常 1-已删除)",
    )

    __table_args__ = (
        # Partial unique index: only enforce name uniqueness among non-deleted
        # rows, so a soft-deleted category does not block recreating the same
        # name. Mirrors migration 002's partial unique index.
        Index(
            "uq_category_user_name_parent",
            "user_id",
            "category_name",
            "parent_id",
            unique=True,
            postgresql_where=text("is_deleted = 0"),
        ),
    )
