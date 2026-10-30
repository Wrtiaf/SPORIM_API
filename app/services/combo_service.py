"""Бизнес-логика комбо-ставок."""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import BetStatus, ComboStatus
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.models.bet import Bet
from app.models.combo import Combo, ComboBet
from app.models.user import User
from app.schemas.combo import ComboCreate

logger = logging.getLogger(__name__)


async def create_combo(db: AsyncSession, user: User, payload: ComboCreate) -> Combo:
    """Собирает комбо из ставок пользователя.

    Правила:
        * все ставки должны принадлежать пользователю и быть в статусе PENDING;
        * одна ставка может входить только в одно комбо;
        * `total_coefficient` — произведение коэффициентов ставок.

    Args:
        db: сессия БД.
        user: владелец ставок.
        payload: список идентификаторов ставок.

    Returns:
        Созданное комбо.

    Raises:
        NotFoundError: часть ставок не найдена.
        ConflictError: ставка уже рассчитана или уже входит в комбо.
    """
    bets = list(
        (
            await db.scalars(
                select(Bet)
                .where(Bet.id.in_(payload.bet_ids), Bet.user_id == user.id)
                .order_by(Bet.id)
            )
        ).all()
    )
    if len(bets) != len(payload.bet_ids):
        raise NotFoundError(
            "Одна или несколько ставок не найдены",
            code="bet_not_found",
        )

    for bet in bets:
        if bet.status is not BetStatus.PENDING:
            raise ConflictError(
                f"Ставка {bet.id} уже рассчитана и не может войти в комбо",
                code="bet_not_pending",
            )

    used_bet_ids = list(
        (await db.scalars(select(ComboBet.bet_id).where(ComboBet.bet_id.in_(payload.bet_ids)))).all()
    )
    if used_bet_ids:
        raise ConflictError(
            f"Ставки уже входят в комбо: {used_bet_ids}",
            code="bet_already_in_combo",
        )

    total_coefficient = 1.0
    for bet in bets:
        total_coefficient *= bet.coefficient

    combo = Combo(
        user_id=user.id,
        total_coefficient=round(total_coefficient, 6),
        status=ComboStatus.ACTIVE,
    )
    db.add(combo)
    await db.flush()
    for bet in bets:
        db.add(ComboBet(combo_id=combo.id, bet_id=bet.id))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "Ставка уже входит в комбо",
            code="bet_already_in_combo",
        ) from exc

    await db.refresh(combo)
    logger.info("Создано комбо id=%s пользователем id=%s", combo.id, user.id)
    return combo


def apply_combo_status(combo: Combo) -> None:
    """Пересчитывает коэффициент и статус комбо по статусам ставок.

    Правила:
        * возвращённые (REFUNDED) ставки исключаются из произведения;
        * если хотя бы одна ставка проиграла — комбо LOST;
        * если все не возвращённые ставки выиграли (и такие есть) — WON;
        * иначе (есть ожидающие или все ставки возвращены) — ACTIVE.
    """
    active_bets = [bet for bet in combo.bets if bet.status is not BetStatus.REFUNDED]

    coefficient = 1.0
    for bet in active_bets:
        coefficient *= bet.coefficient
    combo.total_coefficient = round(coefficient, 6)

    if any(bet.status is BetStatus.LOST for bet in combo.bets):
        combo.status = ComboStatus.LOST
    elif active_bets and all(bet.status is BetStatus.WON for bet in active_bets):
        combo.status = ComboStatus.WON
    else:
        combo.status = ComboStatus.ACTIVE


async def recompute_combos_for_bets(db: AsyncSession, bet_ids: list[int]) -> None:
    """Пересчитывает все комбо, содержащие указанные ставки.

    Вызывается после расчёта или отмены события. Не создаёт выплат:
    выплаты начисляются по каждой ставке отдельно, поэтому повторное
    начисление за одну ставку невозможно.
    """
    if not bet_ids:
        return

    combo_ids = list(
        (
            await db.scalars(
                select(ComboBet.combo_id)
                .where(ComboBet.bet_id.in_(bet_ids))
                .distinct()
            )
        ).all()
    )
    for combo_id in combo_ids:
        combo = await db.scalar(
            select(Combo)
            .where(Combo.id == combo_id)
            .options(selectinload(Combo.bets))
            .execution_options(populate_existing=True)
        )
        if combo is not None:
            apply_combo_status(combo)


async def get_combo_or_404(db: AsyncSession, combo_id: int, user: User) -> Combo:
    """Возвращает комбо с проверкой владельца (модераторы видят все)."""
    combo = await db.get(Combo, combo_id)
    if combo is None:
        raise NotFoundError("Комбо не найдено", code="combo_not_found")
    if combo.user_id != user.id and user.role not in (Role.MODERATOR, Role.ADMIN):
        raise ForbiddenError("Нет доступа к чужому комбо", code="not_combo_owner")
    return combo
