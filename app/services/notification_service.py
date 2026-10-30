"""Заглушка сервиса уведомлений.

Реальная доставка (email/push/websocket) появится позже; пока события
только логируются, чтобы точки интеграции были зафиксированы в коде.
"""

import logging

from app.models.event import Event

logger = logging.getLogger("sporim.notifications")


def notify_user(user_id: int, message: str) -> None:
    """Отправляет уведомление пользователю (заглушка).

    Args:
        user_id: идентификатор получателя.
        message: текст уведомления.
    """
    logger.info("[notification] user_id=%s message=%s", user_id, message)


def notify_event_resolved(event: Event, winning_option_id: int, winners_count: int) -> None:
    """Уведомляет о фиксации исхода события (заглушка)."""
    logger.info(
        "[notification] event_id=%s resolved, winning_option_id=%s, winners=%s",
        event.id,
        winning_option_id,
        winners_count,
    )


def notify_event_cancelled(event: Event, refunded_bets: int) -> None:
    """Уведомляет об отмене события (заглушка)."""
    logger.info(
        "[notification] event_id=%s cancelled, refunded_bets=%s",
        event.id,
        refunded_bets,
    )
