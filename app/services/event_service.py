"""Бизнес-логика событий: создание, редактирование, проценты вариантов."""

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.enums import BetStatus, EventStatus
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


def recalculate_percentages(options: Sequence[Option]) -> None:
    """Пересчитывает `current_percentage` переданных вариантов."""
    for option in options:
        option.current_percentage = calculate_percentage(option.yes_count, option.no_count)


def can_view_event(event: Event, user: User | None) -> bool:
    """Проверяет, доступно ли событие пользователю."""
    if event.deleted_at is not None:
        return False
    if event.status in (EventStatus.ACTIVE, EventStatus.CLOSED):
        return True
    if user is None:
        return False
    if user.role in (Role.MODERATOR, Role.ADMIN):
        return True
    return event.creator_id == user.id


def ensure_event_visible(event: Event, user: User | None) -> None:
    """Скрывает недоступное событие за 404."""
    if not can_view_event(event, user):
        raise NotFoundError("Событие не найдено", code="event_not_found")


async def get_event_or_404(db: AsyncSession, event_id: int) -> Event:
    """Возвращает событие или выбрасывает NotFoundError."""
    event = await db.scalar(
        select(Event).where(Event.id == event_id, Event.deleted_at.is_(None))
    )
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
        ConflictError: событие уже не находится на модерации или отклонено.
    """
    if event.creator_id != user.id and user.role is not Role.ADMIN:
        raise ForbiddenError("Редактировать событие может только автор", code="not_event_owner")
    if event.status not in (EventStatus.PENDING_MODERATION, EventStatus.REJECTED):
        raise ConflictError(
            "Редактировать можно только событие на модерации или отклонённое",
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

    pending_events = await db.scalar(
        select(func.count(Event.id)).where(
            Event.creator_id == creator.id,
            Event.status == EventStatus.PENDING_MODERATION,
            Event.deleted_at.is_(None),
        )
    )
    if int(pending_events or 0) >= settings.MAX_PENDING_EVENTS_PER_USER:
        raise ConflictError(
            "Достигнут лимит событий на модерации",
            code="pending_event_limit",
        )

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
    recalculate_percentages(event.options)
    await db.commit()

    logger.info("Создано событие id=%s автором id=%s", event.id, creator.id)
    return event


async def update_event(
    db: AsyncSession,
    event: Event,
    user: User,
    payload: EventUpdate,
) -> Event:
    """Обновляет событие, находящееся на модерации или отклонённое.

    Если передан список `options`, он полностью заменяет прежние варианты.
    Это безопасно: у такого события ещё не может быть ставок.

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

    nullable_fields = {"description", "image_url", "resolution_source"}
    for field, value in changes.items():
        if value is None and field not in nullable_fields:
            continue
        if field == "title" and value is not None:
            value = value.strip()
        setattr(event, field, value)

    if payload.options is not None:
        event.options.clear()
        event.options.extend(Option(title=option.title) for option in payload.options)
        recalculate_percentages(event.options)

    if event.status is EventStatus.REJECTED:
        event.status = EventStatus.PENDING_MODERATION
        event.rejection_reason = None

    await db.commit()
    await db.refresh(event)
    return event


async def delete_event(db: AsyncSession, event: Event, user: User) -> None:
    """Мягко удаляет событие, находящееся на модерации или отклонённое."""
    ensure_can_edit(event, user)
    event.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("Удалено событие id=%s пользователем id=%s", event.id, user.id)


async def get_event_volumes(db: AsyncSession, event_ids: Sequence[int]) -> dict[int, int]:
    """Возвращает сумму не возвращённых ставок по каждому событию.

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
        .where(Bet.event_id.in_(list(event_ids)), Bet.status != BetStatus.REFUNDED)
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
