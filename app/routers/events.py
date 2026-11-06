"""События: лента, тренды, детали, создание и редактирование."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import and_, func, or_, select

from app.core.enums import BetStatus, EventStatus
from app.core.exceptions import ForbiddenError, ValidationAppError
from app.core.roles import Role
from app.dependencies import CurrentUser, DbSession, LimitParam, OffsetParam, OptionalCurrentUser
from app.models.bet import Bet
from app.models.category import Category
from app.models.event import Event
from app.models.user import User
from app.schemas.common import MessageResponse, Page
from app.schemas.event import EventCreate, EventRead, EventUpdate
from app.services import event_service

router = APIRouter(prefix="/events", tags=["Events"])


def _escape_like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _validate_search(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if len(stripped) < 2:
        raise ValidationAppError(
            "Поисковый запрос должен содержать минимум 2 символа",
            code="search_query_too_short",
        )
    return stripped


def _status_conditions(event_status: EventStatus | None, user: User | None) -> list[object]:
    resolved_status = event_status or EventStatus.ACTIVE
    conditions: list[object] = [Event.status == resolved_status]
    if resolved_status in (EventStatus.ACTIVE, EventStatus.CLOSED):
        return conditions
    if user is None:
        raise ForbiddenError("Нет доступа к событиям в этом статусе", code="event_status_forbidden")
    if user.role not in (Role.MODERATOR, Role.ADMIN):
        conditions.append(Event.creator_id == user.id)
    return conditions


@router.get(
    "",
    response_model=Page[EventRead],
    summary="Лента событий",
    description=(
        "Возвращает события с фильтрами. Если `status` не указан, "
        "показываются только ACTIVE. `search` ищет по title и description."
    ),
)
async def list_events(
    db: DbSession,
    user: OptionalCurrentUser,
    category_slug: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[EventStatus | None, Query(description="Фильтр по статусу")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    creator_id: Annotated[int | None, Query(gt=0, description="Фильтр по автору")] = None,
    sort: Annotated[Literal["new", "volume"], Query(description="Сортировка")] = "new",
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[EventRead]:
    """Возвращает страницу событий."""
    conditions: list[object] = [Event.deleted_at.is_(None)]
    conditions.extend(_status_conditions(status, user))

    if category_slug:
        conditions.append(
            Event.category_id.in_(select(Category.id).where(Category.slug == category_slug))
        )
    if creator_id is not None:
        conditions.append(Event.creator_id == creator_id)
    if search:
        pattern = _escape_like(_validate_search(search) or "")
        conditions.append(
            or_(
                Event.title.ilike(pattern, escape="\\"),
                Event.description.ilike(pattern, escape="\\"),
            )
        )

    total = await db.scalar(select(func.count(Event.id)).where(*conditions)) or 0
    if sort == "volume":
        volume = (
            select(Bet.event_id, func.sum(Bet.amount).label("volume"))
            .where(Bet.status != BetStatus.REFUNDED)
            .group_by(Bet.event_id)
            .subquery()
        )
        stmt = (
            select(Event)
            .outerjoin(volume, volume.c.event_id == Event.id)
            .where(*conditions)
            .order_by(func.coalesce(volume.c.volume, 0).desc(), Event.created_at.desc())
        )
    else:
        stmt = (
            select(Event)
            .where(*conditions)
            .order_by(Event.created_at.desc(), Event.id.desc())
        )

    events = list((await db.scalars(stmt.limit(limit).offset(offset))).all())

    return Page[EventRead](
        items=await event_service.build_event_reads(db, events),
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/trending",
    response_model=list[EventRead],
    summary="Горячие темы",
    description="Топ активных событий по сумме ставок в баллах.",
)
async def trending_events(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=20, description="Сколько событий вернуть")] = 5,
) -> list[EventRead]:
    """Возвращает топ событий по объёму ставок."""
    volume = func.coalesce(func.sum(Bet.amount), 0).label("volume")
    stmt = (
        select(Event, volume)
        .join(
            Bet,
            and_(Bet.event_id == Event.id, Bet.status != BetStatus.REFUNDED),
            isouter=True,
        )
        .where(Event.status == EventStatus.ACTIVE, Event.deleted_at.is_(None))
        .group_by(Event.id)
        .order_by(volume.desc(), Event.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [event_service.build_event_read(event, int(event_volume)) for event, event_volume in rows]


@router.get(
    "/interesting",
    response_model=list[EventRead],
    summary="Интересное",
    description="Активные события с вариантами для секции «Интересное».",
)
async def interesting_events(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=20, description="Сколько событий вернуть")] = 6,
) -> list[EventRead]:
    """Возвращает свежие активные события для карточек."""
    events = list(
        (
            await db.scalars(
                select(Event)
                .where(Event.status == EventStatus.ACTIVE, Event.deleted_at.is_(None))
                .order_by(Event.created_at.desc(), Event.id.desc())
                .limit(limit)
            )
        ).all()
    )
    return await event_service.build_event_reads(db, events)


@router.get(
    "/{event_id}",
    response_model=EventRead,
    summary="Детали события",
    description="Возвращает событие со всеми вариантами, процентами и объёмом ставок.",
    responses={404: {"description": "Событие не найдено"}},
)
async def get_event(event_id: int, db: DbSession, user: OptionalCurrentUser) -> EventRead:
    """Возвращает событие по идентификатору."""
    event = await event_service.get_event_or_404(db, event_id)
    event_service.ensure_event_visible(event, user)
    volumes = await event_service.get_event_volumes(db, [event.id])
    return event_service.build_event_read(event, volumes.get(event.id, 0))


@router.post(
    "",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать событие",
    description=(
        "Создаёт событие в статусе PENDING_MODERATION. Требуется минимум "
        "два варианта исхода. Автор — текущий пользователь."
    ),
    responses={
        401: {"description": "Требуется авторизация"},
        404: {"description": "Категория не найдена"},
    },
)
async def create_event(
    payload: EventCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> EventRead:
    """Создаёт событие от имени текущего пользователя."""
    event = await event_service.create_event(db, current_user, payload)
    return event_service.build_event_read(event)


@router.put(
    "/{event_id}",
    response_model=EventRead,
    summary="Редактировать событие",
    description=(
        "Доступно автору (или администратору) и только пока событие "
        "находится в статусе PENDING_MODERATION или REJECTED."
    ),
    responses={
        403: {"description": "Не автор события"},
        404: {"description": "Событие не найдено"},
        409: {"description": "Событие уже нельзя редактировать"},
    },
)
async def update_event(
    event_id: int,
    payload: EventUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> EventRead:
    """Обновляет событие на модерации или отклонённое событие."""
    event = await event_service.get_event_or_404(db, event_id)
    updated = await event_service.update_event(db, event, current_user, payload)
    volumes = await event_service.get_event_volumes(db, [updated.id])
    return event_service.build_event_read(updated, volumes.get(updated.id, 0))


@router.delete(
    "/{event_id}",
    response_model=MessageResponse,
    summary="Удалить событие",
    description=(
        "Доступно автору (или администратору) и только в статусе "
        "PENDING_MODERATION или REJECTED."
    ),
    responses={
        403: {"description": "Не автор события"},
        404: {"description": "Событие не найдено"},
        409: {"description": "Событие уже нельзя удалить"},
    },
)
async def delete_event(
    event_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Мягко удаляет событие."""
    event = await event_service.get_event_or_404(db, event_id)
    await event_service.delete_event(db, event, current_user)
    return MessageResponse(message=f"Событие {event_id} удалено")
