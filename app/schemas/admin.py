"""Схемы административных операций и статистики платформы."""

from pydantic import BaseModel, Field

from app.core.roles import Role


class AdminUserUpdate(BaseModel):
    """Смена роли пользователя."""

    role: Role = Field(description="USER или MODERATOR")


class BanRequest(BaseModel):
    """Блокировка/разблокировка пользователя."""

    is_active: bool = Field(description="false — заблокировать, true — разблокировать")


class PlatformStats(BaseModel):
    """Агрегированная статистика платформы."""

    users_total: int
    users_active: int
    moderators: int
    admins: int
    categories_total: int

    events_total: int
    events_pending: int
    events_active: int
    events_closed: int
    events_cancelled: int

    bets_total: int
    bets_pending: int
    bets_won: int
    bets_lost: int
    bets_refunded: int

    points_staked_total: int
    points_pending: int
    points_refunded: int
    points_paid_out_gross: int

    complaints_total: int
    complaints_pending: int
