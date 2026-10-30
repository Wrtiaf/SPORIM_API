"""Асинхронный движок SQLAlchemy, фабрика сессий и декларативная база."""

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Единые имена ограничений — чтобы Alembic генерировал стабильные миграции.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс всех ORM-моделей."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: выдаёт асинхронную сессию и откатывает её при ошибке.

    Yields:
        AsyncSession: сессия SQLAlchemy, привязанная к текущему запросу.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:  # noqa: BLE001 - откат обязателен для любой ошибки
            await session.rollback()
            raise
