"""Бизнес-логика ставок."""

import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import BetChoice, BetStatus, EventStatus
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.models.bet import Bet
from app.models.event import Event
from app.models.option import Option
from app.models.user import User
from app.schemas.option import BetCreate
from app.services.event_service import recalculate_percentages

logger = logging.getLogger(__name__)


async def place_bet(
    db: AsyncSession,
    user: User,
    option_id: int,
    payload: BetCreate,
) -> Bet:
    """Размещает ставку на вариант события.

    Порядок операций:
        1. Блокировка строки события (`SELECT ... FOR UPDATE`) и проверка статуса.
        2. Проверка, что пользователь ещё не ставил на это событие.
        3. Атомарное списание баллов (защита от гонок и отрицательного баланса).
        4. Фиксация коэффициента, создание ставки, инкремент счётчика варианта.
        5. Пересчёт процентов всех вариантов события.

    Args:
        db: сессия БД.
        user: текущий пользователь.
        option_id: идентификатор варианта.
        payload: выбор и сумма ставки.

    Returns:
        Созданная ставка.

    Raises:
        NotFoundError: вариант или событие не найдены.
        ConflictError: событие не активно, ставка уже существует или
            недостаточно баллов.
    """
    option = await db.get(Option, option_id)
    if option is None:
        raise NotFoundError("Вариант события не найден", code="option_not_found")

    event = await db.scalar(
        select(Event)
        .where(Event.id == option.event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise NotFoundError("Событие не найдено", code="event_not_found")

    if event.status is not EventStatus.ACTIVE:
        raise ConflictError(
            "Ставки принимаются только по активным событиям",
            code="event_not_active",
        )

    existing_bet = await db.scalar(
        select(Bet.id).where(Bet.user_id == user.id, Bet.event_id == event.id)
    )
    if existing_bet is not None:
        raise ConflictError(
            "Вы уже сделали ставку на это событие",
            code="bet_already_exists",
        )

    debit = await db.execute(
        update(User)
        .where(User.id == user.id, User.balance >= payload.amount, User.is_active.is_(True))
        .values(
            balance=User.balance - payload.amount,
            total_bets=User.total_bets + 1,
        )
    )
    if debit.rowcount == 0:
        raise ConflictError("Недостаточно баллов на балансе", code="insufficient_balance")

    bet = Bet(
        user_id=user.id,
        event_id=event.id,
        option_id=option.id,
        choice=payload.choice,
        amount=payload.amount,
        coefficient=event.fixed_coefficient,
        status=BetStatus.PENDING,
    )
    db.add(bet)

    if payload.choice is BetChoice.YES:
        option.yes_count += 1
    else:
        option.no_count += 1

    recalculate_percentages(event)

    try:
        await db.commit()
    except IntegrityError as exc:
        # Гонка двух одновременных ставок на одно событие: уникальное
        # ограничение (user_id, event_id) откатит и списание баланса.
        await db.rollback()
        raise ConflictError(
            "Вы уже сделали ставку на это событие",
            code="bet_already_exists",
        ) from exc

    await db.refresh(bet)
    await db.refresh(user)
    logger.info(
        "Ставка id=%s: user=%s event=%s option=%s choice=%s amount=%s",
        bet.id,
        user.id,
        event.id,
        option.id,
        bet.choice.value,
        bet.amount,
    )
    return bet


async def get_bet_or_404(db: AsyncSession, bet_id: int, user: User | None = None) -> Bet:
    """Возвращает ставку по id.

    Если передан `user` и он не модератор/администратор, ставка должна
    принадлежать ему.
    """
    bet = await db.get(Bet, bet_id)
    if bet is None:
        raise NotFoundError("Ставка не найдена", code="bet_not_found")
    if (
        user is not None
        and bet.user_id != user.id
        and user.role not in (Role.MODERATOR, Role.ADMIN)
    ):
        raise ForbiddenError("Нет доступа к чужой ставке", code="not_bet_owner")
    return bet


def serialize_bet(bet: Bet) -> dict[str, object]:
    """Вспомогательное представление ставки для логов."""
    return {
        "id": bet.id,
        "user_id": bet.user_id,
        "event_id": bet.event_id,
        "option_id": bet.option_id,
        "choice": bet.choice.value,
        "amount": bet.amount,
        "status": bet.status.value,
        "potential_payout": bet.potential_payout,
    }


__all__ = [
    "get_bet_or_404",
    "place_bet",
    "serialize_bet",
]
