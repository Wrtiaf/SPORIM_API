"""Схемы пользователя и статистики."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.roles import Role
from app.schemas.common import ORMModel


class UserShort(ORMModel):
    """Краткая информация о пользователе."""

    id: int
    username: str


class UserRead(ORMModel):
    """Публичный профиль пользователя."""

    id: int
    username: str
    email: EmailStr
    balance: int
    role: Role
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """Данные для обновления профиля."""

    username: str | None = Field(default=None, min_length=3, max_length=30)
    email: EmailStr | None = None

    @field_validator("username", mode="before")
    @classmethod
    def _strip_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str | None) -> str | None:
        if value is None:
            return value
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
        if not set(value) <= allowed:
            raise ValueError("Допустимы только латинские буквы, цифры, '_', '.' и '-'")
        return value


class BalanceRead(BaseModel):
    """Текущий баланс пользователя."""

    balance: int


class UserStats(BaseModel):
    """Статистика пользователя.

    `win_rate` — процент выигранных ставок среди завершённых (WON + LOST),
    округлённый до двух знаков. Возвращённые ставки и ставки в ожидании
    не учитываются.
    """

    user_id: int
    username: str
    balance: int
    total_bets: int
    won_bets: int
    lost_bets: int
    pending_bets: int
    refunded_bets: int
    win_rate: float
    total_staked: int
    total_won: int
