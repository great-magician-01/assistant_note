"""Note history ORM model + change-type/source constants.

Every mutation of a note (create / update / delete / rollback) records a full
snapshot here, tagged with who made the change (manual vs AI). Snapshots are
append-only — history is never soft-deleted, so the trail of a note survives
even after the note itself is deleted (and powers delete-undo via rollback).

The snapshot stores the *after* state of the note's content fields. ``is_deleted``
and ``search_vector`` are intentionally not snapshotted: rollback always revives
the note (``is_deleted=0``) and recomputes ``search_vector`` from the restored
content.
"""

from sqlalchemy import BigInteger, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.utils.snowflake import snowflake_id

# ── Change type ──────────────────────────────────────────────────────────────
CHANGE_TYPE_CREATE = 1  # 笔记创建
CHANGE_TYPE_UPDATE = 2  # 笔记更新(人为或AI编辑)
CHANGE_TYPE_DELETE = 3  # 笔记删除
CHANGE_TYPE_ROLLBACK = 4  # 从历史快照回滚

# ── Change source ────────────────────────────────────────────────────────────
CHANGE_SOURCE_MANUAL = 1  # 人为操作(通过API)
CHANGE_SOURCE_AI = 2  # AI工具调用


class NoteHistory(Base, TimestampMixin):
    """A single immutable snapshot of a note at a point in time."""

    __tablename__ = "note_histories"

    history_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="历史ID(雪花ID)",
    )
    note_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="笔记ID(应用层校验,无FK)",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属用户ID(冗余便于按用户过滤,无FK)",
    )
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="快照:所属分类ID",
    )
    note_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="快照:笔记标题",
    )
    note_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="快照:笔记正文(Markdown)",
    )
    note_summary: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="快照:AI生成摘要",
    )
    note_tags: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="快照:标签数组",
    )
    note_word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="快照:字数",
    )
    is_pinned: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="快照:是否置顶(0-否 1-是)",
    )
    change_type: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="变更类型(1-创建 2-更新 3-删除 4-回滚)",
    )
    change_source: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=CHANGE_SOURCE_MANUAL,
        server_default="1",
        comment="变更来源(1-人为 2-AI)",
    )
    remark: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="备注(如AI编辑说明)",
    )
