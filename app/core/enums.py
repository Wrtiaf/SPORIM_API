"""Доменные перечисления, общие для моделей, схем и сервисов."""

from enum import Enum


class EventStatus(str, Enum):
    """Статус события."""

    PENDING_MODERATION = "PENDING_MODERATION"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class BetChoice(str, Enum):
    """Выбор пользователя относительно варианта события."""

    YES = "YES"
    NO = "NO"


class BetStatus(str, Enum):
    """Статус ставки."""

    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    REFUNDED = "REFUNDED"


class ComboStatus(str, Enum):
    """Статус комбо-ставки."""

    ACTIVE = "ACTIVE"
    WON = "WON"
    LOST = "LOST"


class ComplaintStatus(str, Enum):
    """Статус жалобы на событие."""

    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
