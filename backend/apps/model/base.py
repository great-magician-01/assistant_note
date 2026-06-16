"""SQLAlchemy declarative base and common column mixins."""

from datetime import datetime

from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.apps.utils.snowflake import snowflake_id


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at columns.

    Timestamps are generated on the application server (Python `datetime.now()`),
    not by the database, so values reflect the backend host's local time.
    """

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )
