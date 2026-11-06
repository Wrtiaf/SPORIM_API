"""Доменные перечисления, общие для моделей, схем и сервисов."""

from enum import Enum


class EventStatus(str, Enum):
    """Статус события."""

    PENDING_MODERATION = "PENDING_MODERATION"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


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


class ComboSide(str, Enum):
    """Сторона комбинированной позиции."""

    YES = "YES"
    NO = "NO"


class ComboLegResult(str, Enum):
    """Результат ноги комбинированной позиции."""

    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    HALF = "HALF"


class ComboStatus(str, Enum):
    """Статус комбинированной позиции."""

    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class ComplaintStatus(str, Enum):
    """Статус жалобы на событие."""

    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class ModerationAction(str, Enum):
    """Действие модератора над событием."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RESOLVE = "RESOLVE"
    CANCEL = "CANCEL"
