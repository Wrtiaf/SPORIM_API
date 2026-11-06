"""Схемы событий."""

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.core.enums import EventStatus
from app.schemas.category import CategoryRead
from app.schemas.common import ORMModel
from app.schemas.option import OptionCreate, OptionRead, OptionShort
from app.schemas.user import UserShort


def _validate_http_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL должен начинаться с http:// или https://")
    return value


class EventCreate(BaseModel):
    """Создание события пользователем."""

    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category_id: int = Field(gt=0)
    image_url: str | None = Field(default=None, max_length=500)
    resolution_source: str | None = Field(default=None, max_length=500)
    fixed_coefficient: float = Field(default=2.0, ge=1.01, le=10.0)
    options: list[OptionCreate] = Field(min_length=2, max_length=10)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Название должно содержать минимум 3 символа")
        return stripped

    @field_validator("image_url", "resolution_source")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return _validate_http_url(value)

    @field_validator("options")
    @classmethod
    def _unique_option_titles(cls, options: list[OptionCreate]) -> list[OptionCreate]:
        titles = [option.title.casefold() for option in options]
        if len(set(titles)) != len(titles):
            raise ValueError("Названия вариантов не должны повторяться")
        return options


class EventUpdate(BaseModel):
    """Редактирование события (доступно только в статусе PENDING_MODERATION)."""

    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category_id: int | None = Field(default=None, gt=0)
    image_url: str | None = Field(default=None, max_length=500)
    resolution_source: str | None = Field(default=None, max_length=500)
    fixed_coefficient: float | None = Field(default=None, ge=1.01, le=10.0)
    options: list[OptionCreate] | None = Field(default=None, min_length=2, max_length=10)

    @field_validator("image_url", "resolution_source")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return _validate_http_url(value)

    @field_validator("options")
    @classmethod
    def _unique_option_titles(
        cls, options: list[OptionCreate] | None
    ) -> list[OptionCreate] | None:
        if options is None:
            return options
        titles = [option.title.casefold() for option in options]
        if len(set(titles)) != len(titles):
            raise ValueError("Названия вариантов не должны повторяться")
        return options


class EventShort(ORMModel):
    """Краткая карточка события."""

    id: int
    title: str
    status: EventStatus
    winning_option_id: int | None = None
    winner: OptionShort | None = None


class EventRead(ORMModel):
    """Полная карточка события с вариантами и объёмом ставок."""

    id: int
    title: str
    description: str | None
    category_id: int
    category: CategoryRead
    creator_id: int
    creator: UserShort
    image_url: str | None
    status: EventStatus
    resolution_source: str | None
    fixed_coefficient: float
    winning_option_id: int | None
    winner: OptionShort | None = None
    rejection_reason: str | None = None
    approved_by: int | None
    approved_at: datetime | None
    created_at: datetime
    closed_at: datetime | None
    resolved_by: int | None
    resolver: UserShort | None = None
    options: list[OptionRead]
    volume: int = Field(default=0, description="Сумма ставок по событию в баллах")
