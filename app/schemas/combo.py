"""Схемы комбинированных позиций."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import BetChoice, ComboLegResult, ComboSide, ComboStatus
from app.schemas.common import ORMModel
from app.schemas.event import EventShort
from app.schemas.option import OptionShort


class ComboLegCreate(BaseModel):
    """Нога создаваемой комбинированной позиции."""

    option_id: int = Field(gt=0)
    choice: BetChoice = Field(description="YES или NO для выбранного варианта")


class ComboCreate(BaseModel):
    """Создание комбинированной позиции."""

    side: ComboSide = Field(description="YES — все ноги выиграют, NO — хотя бы одна проиграет")
    amount: int = Field(ge=1, le=1_000_000)
    legs: list[ComboLegCreate] = Field(min_length=2, max_length=20)

    @field_validator("legs")
    @classmethod
    def _unique_legs(cls, legs: list[ComboLegCreate]) -> list[ComboLegCreate]:
        option_ids = [leg.option_id for leg in legs]
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("option_id не должен повторяться")
        return legs


class ComboLegRead(ORMModel):
    """Нога комбинированной позиции."""

    id: int
    event_id: int
    option_id: int
    choice: BetChoice
    coefficient: float
    result: ComboLegResult
    resolved_at: datetime | None
    event: EventShort
    option: OptionShort


class ComboRead(ORMModel):
    """Комбинированная позиция с ногами."""

    id: int
    user_id: int
    side: ComboSide
    amount: int
    entry_coefficient: float
    potential_payout: int
    payout: int | None
    status: ComboStatus
    created_at: datetime
    settled_at: datetime | None
    legs: list[ComboLegRead]
