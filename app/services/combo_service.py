"""Бизнес-логика комбинированных позиций."""

import logging
import math
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    BetChoice,
    ComboLegResult,
    ComboSide,
    ComboStatus,
    EventStatus,
)
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.money import calculate_payout
from app.core.roles import Role
from app.models.combo import Combo, ComboLeg
from app.models.event import Event
from app.models.option import Option
from app.models.user import User
from app.schemas.combo import ComboCreate

logger = logging.getLogger(__name__)


async def create_combo(db: AsyncSession, user: User, payload: ComboCreate) -> Combo:
    """Создаёт комбинированную позицию с одной ставкой."""
    options = list(
        (
            await db.scalars(
                select(Option)
                .where(Option.id.in_([leg.option_id for leg in payload.legs]))
                .options(selectinload(Option.event))
            )
        ).all()
    )
    if len(options) != len(payload.legs):
        raise NotFoundError("Один или несколько вариантов не найдены", code="option_not_found")

    options_by_id = {option.id: option for option in options}
    event_ids: set[int] = set()
    product = 1.0
    for leg in payload.legs:
        option = options_by_id[leg.option_id]
        event = option.event
        if event.deleted_at is not None or event.status is not EventStatus.ACTIVE:
            raise ConflictError(
                "Комбо можно собрать только по активным событиям",
                code="event_not_active",
            )
        if event.creator_id == user.id:
            raise ForbiddenError("Нельзя включать своё событие в комбо", code="own_event_combo")
        if event.id in event_ids:
            raise ConflictError(
                "В комбо может быть только одна нога на событие",
                code="duplicate_combo_event",
            )
        event_ids.add(event.id)
        product *= event.fixed_coefficient

    product = round(product, 6)
    if payload.side is ComboSide.YES:
        entry_coefficient = product
    else:
        entry_coefficient = round(product / (product - 1), 6)

    debit = await db.execute(
        update(User)
        .where(User.id == user.id, User.balance >= payload.amount, User.is_active.is_(True))
        .values(balance=User.balance - payload.amount)
    )
    if debit.rowcount == 0:
        raise ValidationAppError(
            "Недостаточно баллов на балансе",
            code="insufficient_balance",
        )

    combo = Combo(
        user_id=user.id,
        side=payload.side,
        amount=payload.amount,
        entry_coefficient=entry_coefficient,
        potential_payout=calculate_payout(payload.amount, entry_coefficient),
        status=ComboStatus.ACTIVE,
        legs=[
            ComboLeg(
                event_id=options_by_id[leg.option_id].event_id,
                option_id=leg.option_id,
                choice=leg.choice,
                coefficient=options_by_id[leg.option_id].event.fixed_coefficient,
                result=ComboLegResult.PENDING,
                event=options_by_id[leg.option_id].event,
                option=options_by_id[leg.option_id],
            )
            for leg in payload.legs
        ],
    )
    db.add(combo)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "В комбо может быть только одна нога на событие",
            code="duplicate_combo_event",
        ) from exc

    await db.refresh(combo)
    await db.refresh(user)
    logger.info("Создано комбо id=%s пользователем id=%s", combo.id, user.id)
    return combo


def _leg_fraction(leg: ComboLeg) -> float | None:
    if leg.result is ComboLegResult.WON:
        return 1.0
    if leg.result is ComboLegResult.LOST:
        return 0.0
    if leg.result is ComboLegResult.HALF:
        return 0.5
    return None


def _resolve_leg(leg: ComboLeg, event: Event) -> None:
    if leg.result is not ComboLegResult.PENDING:
        return
    if event.status is EventStatus.CANCELLED:
        leg.result = ComboLegResult.HALF
        leg.resolved_at = datetime.now(timezone.utc)
        return
    if event.status is not EventStatus.CLOSED or event.winning_option_id is None:
        return

    is_winner = (
        leg.choice is BetChoice.YES and leg.option_id == event.winning_option_id
    ) or (leg.choice is BetChoice.NO and leg.option_id != event.winning_option_id)
    leg.result = ComboLegResult.WON if is_winner else ComboLegResult.LOST
    leg.resolved_at = datetime.now(timezone.utc)


async def settle_combo(db: AsyncSession, combo: Combo) -> None:
    """Рассчитывает комбо, если все ноги уже разрешены."""
    if combo.status is not ComboStatus.ACTIVE:
        return

    for leg in combo.legs:
        _resolve_leg(leg, leg.event)

    fractions = [_leg_fraction(leg) for leg in combo.legs]
    if any(fraction is None for fraction in fractions):
        return

    product = math.prod(fraction for fraction in fractions if fraction is not None)
    factor = product if combo.side is ComboSide.YES else 1.0 - product
    payout = calculate_payout(combo.amount, combo.entry_coefficient * factor)

    combo.payout = payout
    combo.status = ComboStatus.SETTLED
    combo.settled_at = datetime.now(timezone.utc)

    if payout > 0:
        await db.execute(
            update(User).where(User.id == combo.user_id).values(balance=User.balance + payout)
        )

    logger.info(
        "Комбо id=%s рассчитано: side=%s payout=%s",
        combo.id,
        combo.side.value,
        payout,
    )


async def recompute_combos_for_events(db: AsyncSession, event_ids: list[int]) -> None:
    """Пересчитывает комбо, содержащие указанные события."""
    if not event_ids:
        return

    combo_ids = list(
        (
            await db.scalars(
                select(ComboLeg.combo_id).where(ComboLeg.event_id.in_(event_ids)).distinct()
            )
        ).all()
    )
    for combo_id in combo_ids:
        combo = await db.scalar(
            select(Combo)
            .where(Combo.id == combo_id)
            .with_for_update()
            .options(
                selectinload(Combo.legs).selectinload(ComboLeg.event),
                selectinload(Combo.legs).selectinload(ComboLeg.option),
            )
            .execution_options(populate_existing=True)
        )
        if combo is not None:
            await settle_combo(db, combo)


async def get_combo_or_404(db: AsyncSession, combo_id: int, user: User) -> Combo:
    """Возвращает комбо с проверкой владельца (модераторы видят все)."""
    combo = await db.get(Combo, combo_id)
    if combo is None:
        raise NotFoundError("Комбо не найдено", code="combo_not_found")
    if combo.user_id != user.id and user.role not in (Role.MODERATOR, Role.ADMIN):
        raise NotFoundError("Комбо не найдено", code="combo_not_found")
    return combo
