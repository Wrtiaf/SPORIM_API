"""Схемы вариантов события и создания ставки."""

from pydantic import BaseModel, Field, field_validator

from app.core.enums import BetChoice
from app.schemas.common import ORMModel


class OptionCreate(BaseModel):
    """Вариант исхода при создании события."""

    title: str = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Название варианта не может быть пустым")
        return stripped


class OptionRead(ORMModel):
    """Вариант исхода с текущими процентами."""

    id: int
    event_id: int
    title: str
    yes_count: int
    no_count: int
    current_percentage: float


class BetCreate(BaseModel):
    """Данные для размещения ставки."""

    choice: BetChoice = Field(description="YES — вариант победит, NO — не победит")
    amount: int = Field(ge=1, le=1_000_000, description="Размер ставки в баллах")
