"""Профиль, баланс, статистика и история текущего пользователя."""

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.enums import BetStatus
from app.core.exceptions import ConflictError
from app.core.money import calculate_payout
from app.dependencies import CurrentUser, DbSession, LimitParam, OffsetParam
from app.models.bet import Bet
from app.models.event import Event
from app.schemas.bet import BetRead
from app.schemas.common import Page
from app.schemas.event import EventRead
from app.schemas.user import BalanceRead, UserRead, UserStats, UserUpdate
from app.services.event_service import build_event_reads

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserRead,
    summary="Мой профиль",
    responses={401: {"description": "Требуется авторизация"}},
)
async def get_me(current_user: CurrentUser) -> UserRead:
    """Возвращает профиль текущего пользователя."""
    return UserRead.model_validate(current_user)


@router.put(
    "/me",
    response_model=UserRead,
    summary="Обновить профиль",
    description="Позволяет изменить username и/или email. Оба поля уникальны.",
    responses={
        401: {"description": "Требуется авторизация"},
        409: {"description": "username или email уже заняты"},
    },
)
async def update_me(
    payload: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> UserRead:
    """Обновляет профиль текущего пользователя."""
    changes = payload.model_dump(exclude_unset=True)

    if changes.get("username") is not None:
        current_user.username = changes["username"].strip()
    if changes.get("email") is not None:
        current_user.email = str(changes["email"]).lower()

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "Пользователь с таким username или email уже существует",
            code="user_already_exists",
        ) from exc

    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.get(
    "/me/balance",
    response_model=BalanceRead,
    summary="Текущий баланс",
)
async def get_my_balance(current_user: CurrentUser, db: DbSession) -> BalanceRead:
    """Возвращает актуальный баланс баллов."""
    # Перечитываем баланс, чтобы не отдавать устаревшее значение из identity map.
    await db.refresh(current_user, attribute_names=["balance"])
    return BalanceRead(balance=current_user.balance)


@router.get(
    "/me/stats",
    response_model=UserStats,
    summary="Моя статистика",
    description=(
        "`win_rate` — доля выигранных среди завершённых ставок (WON + LOST) "
        "в процентах; возвращённые и ожидающие ставки не учитываются."
    ),
)
async def get_my_stats(current_user: CurrentUser, db: DbSession) -> UserStats:
    """Возвращает агрегированную статистику пользователя."""
    rows = (
        await db.execute(
            select(
                Bet.status,
                func.count(Bet.id),
                func.coalesce(func.sum(Bet.amount), 0),
            )
            .where(Bet.user_id == current_user.id)
            .group_by(Bet.status)
        )
    ).all()

    counts: dict[BetStatus, int] = {}
    amounts: dict[BetStatus, int] = {}
    for bet_status, count, amount in rows:
        counts[bet_status] = int(count)
        amounts[bet_status] = int(amount)

    won = counts.get(BetStatus.WON, 0)
    lost = counts.get(BetStatus.LOST, 0)
    finished = won + lost

    won_rows = (
        await db.execute(
            select(Bet.amount, Bet.coefficient).where(
                Bet.user_id == current_user.id,
                Bet.status == BetStatus.WON,
            )
        )
    ).all()
    total_won = sum(calculate_payout(int(amount), float(coefficient)) for amount, coefficient in won_rows)

    return UserStats(
        user_id=current_user.id,
        username=current_user.username,
        balance=current_user.balance,
        total_bets=sum(counts.values()),
        won_bets=won,
        lost_bets=lost,
        pending_bets=counts.get(BetStatus.PENDING, 0),
        refunded_bets=counts.get(BetStatus.REFUNDED, 0),
        win_rate=round(won / finished * 100, 2) if finished else 0.0,
        total_staked=sum(amounts.values()),
        total_won=total_won,
    )


@router.get(
    "/me/bets",
    response_model=Page[BetRead],
    summary="Мои ставки",
    description="История ставок текущего пользователя с пагинацией.",
)
async def get_my_bets(
    current_user: CurrentUser,
    db: DbSession,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[BetRead]:
    """Возвращает ставки пользователя (свежие первыми)."""
    conditions = [Bet.user_id == current_user.id]

    total = await db.scalar(select(func.count(Bet.id)).where(*conditions)) or 0
    bets = list(
        (
            await db.scalars(
                select(Bet)
                .where(*conditions)
                .order_by(Bet.created_at.desc(), Bet.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )

    return Page[BetRead](
        items=[BetRead.model_validate(bet) for bet in bets],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/me/events",
    response_model=Page[EventRead],
    summary="Мои события",
    description="События, созданные текущим пользователем, во всех статусах.",
)
async def get_my_events(
    current_user: CurrentUser,
    db: DbSession,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[EventRead]:
    """Возвращает созданные пользователем события."""
    conditions = [Event.creator_id == current_user.id]

    total = await db.scalar(select(func.count(Event.id)).where(*conditions)) or 0
    events = list(
        (
            await db.scalars(
                select(Event)
                .where(*conditions)
                .order_by(Event.created_at.desc(), Event.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )

    return Page[EventRead](
        items=await build_event_reads(db, events),
        total=int(total),
        limit=limit,
        offset=offset,
    )
