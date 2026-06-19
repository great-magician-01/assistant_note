"""AI chat session & message ORM models.

Server-managed chat history. A session snapshots the config/model/api_format at
first message time so a running conversation keeps its provider behavior even if
the pool/config is later edited. Messages cover three roles (user/assistant/tool)
in one table: assistant rows may carry ``tool_calls`` (the calls the model
requested), and tool rows carry the matching ``tool_call_id`` / ``tool_name`` /
result ``content`` — so both conversation history and tool-call situations are
persisted (per the feature requirement).
"""

from sqlalchemy import BigInteger, Index, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.utils.snowflake import snowflake_id

# Message roles.
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"


class AiChatSession(Base, TimestampMixin):
    """A chat conversation owned by a user."""

    __tablename__ = "ai_chat_sessions"

    session_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="会话ID(雪花ID)",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属用户ID(应用层校验,无FK)",
    )
    config_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="快照:使用的AI配置ID(无FK)",
    )
    model_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="快照:使用的模型池ID(无FK)",
    )
    api_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="快照:接口格式(openai/anthropic)",
    )
    session_title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="新对话",
        server_default="新对话",
        comment="会话标题(默认新对话,首条消息后自动取前30字)",
    )
    note_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        comment="绑定的笔记ID(可空;笔记AI助手会话用,应用层校验,无FK)",
    )
    is_deleted: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否删除(0-正常 1-已删除)",
    )

    __table_args__ = (
        Index("ix_ai_chat_sessions_user_created", "user_id", "created_at"),
        Index("ix_ai_chat_sessions_note", "note_id", "is_deleted"),
    )


class AiChatMessage(Base, TimestampMixin):
    """One message in a chat session (user / assistant / tool)."""

    __tablename__ = "ai_chat_messages"

    message_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="消息ID(雪花ID)",
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属会话ID(应用层校验,无FK)",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="角色(user/assistant/tool)",
    )
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="文本内容(user/assistant正文;tool为结果文本)",
    )
    tool_calls: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="assistant请求工具:[{id,name,arguments{}}]",
    )
    tool_call_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="role=tool:对应的tool_call id",
    )
    tool_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="role=tool:工具名",
    )
    is_error: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="role=tool:工具执行是否出错(0-否 1-是)",
    )
    prompt_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="assistant行:输入token(该轮)",
    )
    completion_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="assistant行:输出token(该轮)",
    )
    iter_index: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="该消息属于第几次模型调用(0=首条user,1..N=模型轮次)",
    )

    __table_args__ = (
        Index("ix_ai_chat_messages_session_created", "session_id", "created_at"),
        Index("ix_ai_chat_messages_session_iter", "session_id", "iter_index"),
    )
