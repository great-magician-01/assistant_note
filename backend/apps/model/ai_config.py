"""AI model runtime config ORM model (global, no user_id).

A config picks one model from the pool (``model_id``) and layers runtime
parameters on top: system prompt, enabled tools, JSON-output toggle, sampling.
``is_default`` is constrained to a single row globally via a partial unique
index (see migration 003).
"""

from sqlalchemy import (
    BigInteger,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.utils.snowflake import snowflake_id


class AiConfig(Base, TimestampMixin):
    __tablename__ = "ai_configs"

    config_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="配置ID",
    )
    config_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="配置名",
    )
    model_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="引用模型池ID(NULL=未绑定模型,应用层校验,无FK)",
    )
    system_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="系统提示词",
    )
    tools: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        server_default="[]",
        comment="可用工具名数组",
    )
    json_output: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否强制JSON输出(0-否 1-是)",
    )
    temperature: Mapped[float | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
        comment="温度(0-2)",
    )
    top_p: Mapped[float | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
        comment="nucleus sampling",
    )
    max_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="覆盖模型池max_tokens(NULL=用模型池值)",
    )
    is_default: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否默认配置(0-否 1-是)",
    )
    is_active: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="是否启用(0-禁用 1-启用)",
    )
    is_deleted: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否删除(0-正常 1-已删除)",
    )

    __table_args__ = (
        # Global at most one default config among non-deleted rows.
        Index(
            "uq_ai_configs_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default = 1 AND is_deleted = 0"),
        ),
    )
