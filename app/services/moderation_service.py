"""Модерация событий: одобрение, отклонение, фиксация исхода, отмена."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    BetChoice,
    BetStatus,
    ComplaintStatus,
    EventStatus,
    ModerationAction,
)
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.money import calculate_payout
from app.models.bet import Bet
from app.models.complaint import Complaint
from app.models.event import Event
from app.models.moderation_log import ModerationLog
from app.models.user import User
from app.services import notification_service
from app.services.combo_service import recompute_combos_for_events

logger = logging.getLogger(__name__)


async def lock_event(db: AsyncSession, event_id: int) -> Event:
    """Загружает событие с блокировкой строки.

    Блокировка сериализует approve/reject/resolve/cancel, поэтому повторный
    вызов не сможет начислить выплаты дважды.
    """
    event = await db.scalar(
        select(Event)
        .where(Event.id == event_id, Event.deleted_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise NotFoundError("Событие не найдено", code="event_not_found")
    return event


def _ensure_not_own_event(event: Event, moderator: User) -> None:
    if event.creator_id == moderator.id:
        raise ForbiddenError(
            "Нельзя модерировать собственное событие",
            code="self_moderation_forbidden",
        )


def _log_action(
    db: AsyncSession,
    event: Event,
    moderator: User,
    action: ModerationAction,
    reason: str | None = None,
) -> None:
    db.add(
        ModerationLog(
            event_id=event.id,
            moderator_id=moderator.id,
            action=action,
            reason=reason,
        )
    )


async def approve_event(
    db: AsyncSession,
    event_id: int,
    moderator: User,
    fixed_coefficient: float | None = None,
) -> Event:
    """Одобряет событие: PENDING_MODERATION -> ACTIVE."""
    event = await lock_event(db, event_id)
    if event.status is not EventStatus.PENDING_MODERATION:
        raise ConflictError(
            "Одобрить можно только событие на модерации",
            code="event_not_pending",
        )
    _ensure_not_own_event(event, moderator)

    if fixed_coefficient is not None:
        event.fixed_coefficient = fixed_coefficient
    event.status = EventStatus.ACTIVE
    event.approved_by = moderator.id
    event.approved_at = datetime.now(timezone.utc)
    _log_action(db, event, moderator, ModerationAction.APPROVE)

    await db.commit()
    await db.refresh(event)
    logger.info("Событие id=%s одобрено", event.id)
    return event


async def reject_event(db: AsyncSession, event_id: int, moderator: User, reason: str) -> Event:
    """Отклоняет событие: PENDING_MODERATION -> REJECTED."""
    event = await lock_event(db, event_id)
    if event.status is not EventStatus.PENDING_MODERATION:
        raise ConflictError(
            "Отклонить можно только событие на модерации",
            code="event_not_pending",
        )
    _ensure_not_own_event(event, moderator)

    event.status = EventStatus.REJECTED
    event.rejection_reason = reason
    _log_action(db, event, moderator, ModerationAction.REJECT, reason)

    await db.commit()
    await db.refresh(event)
    logger.info("Событие id=%s отклонено: %s", event.id, reason)
    return event


async def resolve_event(
    db: AsyncSession,
    event_id: int,
    moderator: User,
    winning_option_id: int,
) -> Event:
    """Фиксирует победный вариант и начисляет выплаты.

    Ставка выигрывает, если:
        * `choice == YES` и `option_id == winning_option_id`;
        * `choice == NO` и `option_id != winning_option_id`.

    Args:
        db: сессия БД.
        event_id: идентификатор события.
        moderator: модератор/администратор, фиксирующий исход.
        winning_option_id: идентификатор победного варианта.

    Returns:
        Закрытое событие.

    Raises:
        ConflictError: событие не активно (в том числе при повторной фиксации).
        ValidationAppError: вариант не принадлежит событию.
        ForbiddenError: модератор является автором события.
    """
    event = await lock_event(db, event_id)
    if event.status is not EventStatus.ACTIVE:
        raise ConflictError(
            "Зафиксировать исход можно только у активного события",
            code="event_not_active",
        )
    _ensure_not_own_event(event, moderator)

    winning_option = next(
        (option for option in event.options if option.id == winning_option_id),
        None,
    )
    if winning_option is None:
        raise ValidationAppError(
            "Вариант не принадлежит этому событию",
            code="invalid_winning_option",
        )

    pending_bets = list(
        (
            await db.scalars(
                select(Bet).where(
                    Bet.event_id == event.id,
                    Bet.status == BetStatus.PENDING,
                )
            )
        ).all()
    )

    winners = 0
    for bet in pending_bets:
        is_winner = (
            bet.choice is BetChoice.YES and bet.option_id == winning_option_id
        ) or (bet.choice is BetChoice.NO and bet.option_id != winning_option_id)

        if not is_winner:
            bet.status = BetStatus.LOST
            continue

        payout = calculate_payout(bet.amount, bet.coefficient)
        bet.status = BetStatus.WON
        winners += 1
        await db.execute(
            update(User)
            .where(User.id == bet.user_id)
            .values(balance=User.balance + payout)
        )

    event.status = EventStatus.CLOSED
    event.closed_at = datetime.now(timezone.utc)
    event.winning_option_id = winning_option_id
    event.resolved_by = moderator.id
    _log_action(db, event, moderator, ModerationAction.RESOLVE)

    await db.flush()
    await recompute_combos_for_events(db, [event.id])

    await db.commit()
    await db.refresh(event)
    logger.info(
        "Событие id=%s закрыто: победил вариант id=%s, выиграло ставок=%s",
        event.id,
        winning_option_id,
        winners,
    )
    notification_service.notify_event_resolved(event, winning_option_id, winners)
    return event


async def cancel_event(db: AsyncSession, event_id: int, moderator: User) -> Event:
    """Отменяет активное событие и возвращает баллы по ожидающим ставкам."""
    event = await lock_event(db, event_id)
    if event.status not in (EventStatus.PENDING_MODERATION, EventStatus.ACTIVE):
        raise ConflictError(
            "Отменить можно только событие на модерации или активное",
            code="event_not_cancellable",
        )
    _ensure_not_own_event(event, moderator)

    refunded = await _cancel_and_refund(db, event, moderator)
    _log_action(db, event, moderator, ModerationAction.CANCEL)

    await db.flush()
    await recompute_combos_for_events(db, [event.id])

    await db.commit()
    await db.refresh(event)
    logger.info("Событие id=%s отменено, возвращено ставок=%s", event.id, refunded)
    notification_service.notify_event_cancelled(event, refunded)
    return event


async def _cancel_and_refund(db: AsyncSession, event: Event, moderator: User) -> int:
    """Переводит событие в CANCELLED и возвращает баллы по PENDING-ставкам.

    Returns:
        Количество возвращённых ставок.
    """
    pending_bets = list(
        (
            await db.scalars(
                select(Bet).where(
                    Bet.event_id == event.id,
                    Bet.status == BetStatus.PENDING,
                )
            )
        ).all()
    )

    for bet in pending_bets:
        bet.status = BetStatus.REFUNDED
        await db.execute(
            update(User)
            .where(User.id == bet.user_id)
            .values(balance=User.balance + bet.amount)
        )

    event.status = EventStatus.CANCELLED
    event.closed_at = datetime.now(timezone.utc)
    event.resolved_by = moderator.id
    return len(pending_bets)


async def get_complaint_or_404(db: AsyncSession, complaint_id: int) -> Complaint:
    """Возвращает жалобу или выбрасывает NotFoundError."""
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise NotFoundError("Жалоба не найдена", code="complaint_not_found")
    return complaint


async def resolve_complaint(
    db: AsyncSession,
    complaint_id: int,
    moderator: User,
    new_status: ComplaintStatus,
    resolution_comment: str | None = None,
) -> Complaint:
    """Переводит жалобу в RESOLVED или REJECTED."""
    complaint = await get_complaint_or_404(db, complaint_id)
    if complaint.status is not ComplaintStatus.PENDING:
        raise ConflictError(
            "Жалоба уже обработана",
            code="complaint_already_resolved",
        )

    complaint.status = new_status
    complaint.resolved_at = datetime.now(timezone.utc)
    complaint.resolved_by = moderator.id
    complaint.resolution_comment = resolution_comment
    await db.commit()
    await db.refresh(complaint)
    logger.info("Жалоба id=%s обработана: %s", complaint.id, new_status.value)
    return complaint
