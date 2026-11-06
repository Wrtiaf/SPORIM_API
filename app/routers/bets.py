"""Варианты события и ставки."""

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.dependencies import (
    CurrentUser,
    DbSession,
    LimitParam,
    OffsetParam,
    OptionalCurrentUser,
)
from app.models.bet import Bet
from app.models.option import Option
from app.schemas.bet import BetRead
from app.schemas.common import Page
from app.schemas.option import BetCreate, OptionRead
from app.services import bet_service, event_service

router = APIRouter(tags=["Bets"])


@router.get(
    "/events/{event_id}/options",
    response_model=list[OptionRead],
    summary="Варианты события",
    description="Возвращает варианты события с количеством голосов и процентами.",
    responses={404: {"description": "Событие не найдено"}},
)
async def get_event_options(
    event_id: int,
    db: DbSession,
    user: OptionalCurrentUser,
) -> list[OptionRead]:
    """Возвращает варианты указанного события."""
    event = await event_service.get_event_or_404(db, event_id)
    event_service.ensure_event_visible(event, user)
    options = (
        await db.scalars(select(Option).where(Option.event_id == event_id).order_by(Option.id))
    ).all()
    return [OptionRead.model_validate(option) for option in options]


@router.post(
    "/options/{option_id}/bet",
    response_model=BetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Сделать ставку",
    description=(
        "Списывает баллы, фиксирует текущий коэффициент события и пересчитывает "
        "проценты вариантов. Один пользователь может поставить на событие "
        "только один раз."
    ),
    responses={
        401: {"description": "Требуется авторизация"},
        404: {"description": "Вариант не найден"},
        409: {"description": "Событие не активно или ставка уже существует"},
        422: {"description": "Недостаточно баллов"},
    },
)
async def place_bet(
    option_id: int,
    payload: BetCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> BetRead:
    """Размещает ставку на вариант события."""
    bet = await bet_service.place_bet(db, current_user, option_id, payload)
    return BetRead.model_validate(bet)


@router.get(
    "/bets",
    response_model=Page[BetRead],
    summary="Мои ставки",
    description="Дублирует `/users/me/bets` для удобства фронтенда.",
)
async def list_my_bets(
    current_user: CurrentUser,
    db: DbSession,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[BetRead]:
    """Возвращает ставки текущего пользователя."""
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
    "/bets/{bet_id}",
    response_model=BetRead,
    summary="Детали ставки",
    description="Автор ставки, модератор или администратор может посмотреть детали.",
    responses={
        404: {"description": "Ставка не найдена"},
    },
)
async def get_bet(bet_id: int, current_user: CurrentUser, db: DbSession) -> BetRead:
    """Возвращает детали ставки."""
    bet = await bet_service.get_bet_or_404(db, bet_id, current_user)
    return BetRead.model_validate(bet)
