"""Бизнес-логика событий: создание, редактирование, проценты вариантов."""

import logging
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventStatus
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.models.bet import Bet
from app.models.category import Category
from app.models.event import Event
from app.models.option import Option
from app.models.user import User
from app.schemas.event import EventCreate, EventRead, EventUpdate

logger = logging.getLogger(__name__)


def calculate_percentage(yes_count: int, no_count: int) -> float:
    """Считает процент «Да» для одного варианта.

    Формула: `yes_count / (yes_count + no_count) * 100`. Проценты вариантов
    независимы и не обязаны суммироваться в 100: каждый вариант — отдельный
    рынок «Да/Нет».

    Args:
        yes_count: количество ставок «Да» на вариант.
        no_count: количество ставок «Нет» на вариант.

    Returns:
        Процент от 0 до 100, округлённый до двух знаков.
    """
    total = yes_count + no_count
    if total <= 0:
        return 0.0
    return round(yes_count / total * 100, 2)


def recalculate_percentages(event: Event) -> None:
    """Пересчитывает `current_percentage` всех вариантов события."""
    for option in event.options:
        option.current_percentage = calculate_percentage(option.yes_count, option.no_count)


async def get_event_or_404(db: AsyncSession, event_id: int) -> Event:
    """Возвращает событие или выбрасывает NotFoundError."""
    event = await db.get(Event, event_id)
    if event is None:
        raise NotFoundError("Событие не найдено", code="event_not_found")
    return event


async def get_category_or_404(db: AsyncSession, category_id: int) -> Category:
    """Возвращает категорию или выбрасывает NotFoundError."""
    category = await db.get(Category, category_id)
    if category is None:
        raise NotFoundError("Категория не найдена", code="category_not_found")
    return category


def ensure_can_edit(event: Event, user: User) -> None:
    """Проверяет, что пользователь может редактировать событие.

    Raises:
        ForbiddenError: пользователь не автор и не администратор.
        ConflictError: событие уже не находится на модерации.
    """
    if event.creator_id != user.id and user.role is not Role.ADMIN:
        raise ForbiddenError("Редактировать событие может только автор", code="not_event_owner")
    if event.status is not EventStatus.PENDING_MODERATION:
        raise ConflictError(
            "Редактировать можно только событие на модерации",
            code="event_not_editable",
        )


async def create_event(db: AsyncSession, creator: User, payload: EventCreate) -> Event:
    """Создаёт событие в статусе PENDING_MODERATION.

    Args:
        db: сессия БД.
        creator: автор события.
        payload: данные события.

    Returns:
        Созданное событие с вариантами.
    """
    await get_category_or_404(db, payload.category_id)

    event = Event(
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        creator_id=creator.id,
        image_url=payload.image_url,
        resolution_source=payload.resolution_source,
        fixed_coefficient=payload.fixed_coefficient,
        status=EventStatus.PENDING_MODERATION,
        options=[Option(title=option.title) for option in payload.options],
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    recalculate_percentages(event)
    await db.commit()

    logger.info("Создано событие id=%s автором id=%s", event.id, creator.id)
    return event


async def update_event(
    db: AsyncSession,
    event: Event,
    user: User,
    payload: EventUpdate,
) -> Event:
    """Обновляет событие, находящееся на модерации.

    Если передан список `options`, он полностью заменяет прежние варианты.
    Это безопасно: у события на модерации ещё не может быть ставок.

    Args:
        db: сессия БД.
        event: редактируемое событие.
        user: текущий пользователь.
        payload: изменения.

    Returns:
        Обновлённое событие.
    """
    ensure_can_edit(event, user)

    changes = payload.model_dump(exclude_unset=True, exclude={"options"})
    if "category_id" in changes and changes["category_id"] is not None:
        await get_category_or_404(db, changes["category_id"])

    for field, value in changes.items():
        if field == "title" and value is not None:
            value = value.strip()
        setattr(event, field, value)

    if payload.options is not None:
        event.options.clear()
        event.options.extend(Option(title=option.title) for option in payload.options)
        recalculate_percentages(event)

    await db.commit()
    await db.refresh(event)
    return event


async def delete_event(db: AsyncSession, event: Event, user: User) -> None:
    """Удаляет событие, находящееся на модерации."""
    ensure_can_edit(event, user)
    await db.delete(event)
    await db.commit()
    logger.info("Удалено событие id=%s пользователем id=%s", event.id, user.id)


async def get_event_volumes(db: AsyncSession, event_ids: Sequence[int]) -> dict[int, int]:
    """Возвращает сумму ставок по каждому событию.

    Args:
        db: сессия БД.
        event_ids: идентификаторы событий.

    Returns:
        Словарь `event_id -> сумма ставок` (0, если ставок нет).
    """
    if not event_ids:
        return {}

    stmt = (
        select(Bet.event_id, func.coalesce(func.sum(Bet.amount), 0))
        .where(Bet.event_id.in_(list(event_ids)))
        .group_by(Bet.event_id)
    )
    rows = (await db.execute(stmt)).all()
    return {int(event_id): int(volume) for event_id, volume in rows}


def build_event_read(event: Event, volume: int = 0) -> EventRead:
    """Собирает схему события с объёмом ставок."""
    result = EventRead.model_validate(event)
    result.volume = volume
    return result


async def build_event_reads(db: AsyncSession, events: Sequence[Event]) -> list[EventRead]:
    """Собирает список схем событий, подгружая объёмы одним запросом."""
    volumes = await get_event_volumes(db, [event.id for event in events])
    return [build_event_read(event, volumes.get(event.id, 0)) for event in events]
