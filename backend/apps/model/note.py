"""Note ORM model."""

from sqlalchemy import (
    BigInteger,
    Integer,
    SmallInteger,
    String,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.utils.snowflake import snowflake_id


class Note(Base, TimestampMixin):
    __tablename__ = "notes"

    note_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="笔记ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属用户ID",
    )
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="所属分类ID",
    )
    note_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="笔记标题",
    )
    note_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Markdown内容",
    )
    note_summary: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="AI生成摘要",
    )
    note_tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        server_default="[]",
        comment="标签数组",
    )
    is_pinned: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否置顶(0-否 1-是)",
    )
    is_deleted: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否删除(0-正常 1-已删除)",
    )
    note_word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="字数统计",
    )
    # Populated by the app on create/update from jieba-segmented title+content.
    # deferred=True so normal queries don't SELECT this large TSVECTOR column.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        nullable=True,
        deferred=True,
        comment="全文搜索向量",
    )

    __table_args__ = (
        Index(
            "ix_notes_user_deleted_updated",
            "user_id",
            "is_deleted",
            "updated_at",
        ),
    )
