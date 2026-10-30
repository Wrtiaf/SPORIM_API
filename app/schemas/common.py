"""Общие схемы: базовый ORM-класс, пагинация, служебные ответы."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Базовая схема с поддержкой сериализации ORM-объектов."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Универсальный ответ с пагинацией."""

    items: list[T] = Field(description="Элементы текущей страницы")
    total: int = Field(description="Общее количество элементов")
    limit: int = Field(description="Размер страницы")
    offset: int = Field(description="Смещение")


class MessageResponse(BaseModel):
    """Простой ответ с сообщением."""

    success: bool = True
    message: str
