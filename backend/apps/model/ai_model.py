"""AI model pool ORM model (global, no user_id)."""

from sqlalchemy import (
    BigInteger,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.apps.model.base import Base, TimestampMixin
from backend.apps.utils.snowflake import snowflake_id


class AiModel(Base, TimestampMixin):
    """A provider model entry in the global model pool.

    Stores the connection info (base_url, api_key, model id, API format) needed
    to call the model. ``ai_configs`` reference a row here and layer runtime
    parameters (prompt, tools, temperature, ...) on top.
    """

    __tablename__ = "ai_models"

    model_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        default=snowflake_id,
        comment="模型ID",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="友好显示名",
    )
    api_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="接口格式(openai/anthropic)",
    )
    base_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="API基址",
    )
    api_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="密钥(明文)",
    )
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="实际模型ID(传给API的字符串)",
    )
    is_multimodal: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="是否多模态(0-否 1-是)",
    )
    max_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4096,
        server_default="4096",
        comment="单次最大输出token",
    )
    remark: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="备注",
    )
    extra_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        server_default="{}",
        comment="额外参数(自定义请求头等)",
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
        Index("ix_ai_models_is_deleted", "is_deleted"),
    )
