"""Схемы комбо-ставок."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import ComboStatus
from app.schemas.bet import BetRead
from app.schemas.common import ORMModel


class ComboCreate(BaseModel):
    """Создание комбо из списка ставок."""

    bet_ids: list[int] = Field(min_length=1, max_length=20)

    @field_validator("bet_ids")
    @classmethod
    def _unique_bet_ids(cls, bet_ids: list[int]) -> list[int]:
        if len(set(bet_ids)) != len(bet_ids):
            raise ValueError("bet_ids не должен содержать повторов")
        if any(bet_id <= 0 for bet_id in bet_ids):
            raise ValueError("bet_ids должен содержать положительные идентификаторы")
        return bet_ids


class ComboRead(ORMModel):
    """Комбо с входящими ставками."""

    id: int
    user_id: int
    total_coefficient: float
    status: ComboStatus
    created_at: datetime
    bets: list[BetRead]
