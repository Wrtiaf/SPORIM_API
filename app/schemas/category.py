"""Схемы категорий."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class CategoryCreate(BaseModel):
    """Создание категории."""

    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    @field_validator("name", "slug", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CategoryUpdate(BaseModel):
    """Обновление категории."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class CategoryRead(ORMModel):
    """Категория."""

    id: int
    name: str
    slug: str
    created_at: datetime
