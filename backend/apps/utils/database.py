"""Async database engine, session factory, and FastAPI dependency."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.apps.utils.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    # Tables live in a non-default schema (DB_SCHEMA, e.g. "note_db"). The
    # server's search_path does not include it, so asyncpg must be told to set
    # it per connection — otherwise unqualified table names (e.g. "users")
    # raise UndefinedTableError. asyncpg applies server_settings on connect.
    connect_args={"server_settings": {"search_path": settings.DB_SCHEMA}},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.warning("DB session rolled back due to exception", exc_info=True)
            await session.rollback()
            raise
