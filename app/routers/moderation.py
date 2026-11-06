"""Модерация событий и жалоб (MODERATOR, ADMIN)."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ComplaintStatus, EventStatus
from app.dependencies import DbSession, LimitParam, ModeratorUser, OffsetParam
from app.models.complaint import Complaint
from app.models.event import Event
from app.schemas.common import Page
from app.schemas.complaint import ComplaintRead
from app.schemas.event import EventRead
from app.schemas.moderation import (
    ApproveEventRequest,
    ComplaintResolveRequest,
    RejectEventRequest,
    ResolveEventRequest,
)
from app.services import event_service, moderation_service

router = APIRouter(prefix="/moderation", tags=["Moderation"])


async def _event_read(db: AsyncSession, event: Event) -> EventRead:
    """Собирает EventRead с объёмом ставок."""
    volumes = await event_service.get_event_volumes(db, [event.id])
    return event_service.build_event_read(event, volumes.get(event.id, 0))


@router.get(
    "/events/pending",
    response_model=Page[EventRead],
    summary="События на модерации",
    description="Возвращает события в статусе PENDING_MODERATION (сначала старые).",
    responses={403: {"description": "Недостаточно прав"}},
)
async def list_pending_events(
    _: ModeratorUser,
    db: DbSession,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[EventRead]:
    """Возвращает очередь модерации."""
    conditions = [
        Event.status == EventStatus.PENDING_MODERATION,
        Event.deleted_at.is_(None),
    ]

    total = await db.scalar(select(func.count(Event.id)).where(*conditions)) or 0
    events = list(
        (
            await db.scalars(
                select(Event)
                .where(*conditions)
                .order_by(Event.created_at.asc(), Event.id.asc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )

    return Page[EventRead](
        items=await event_service.build_event_reads(db, events),
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/events/{event_id}/approve",
    response_model=EventRead,
    summary="Одобрить событие",
    description="PENDING_MODERATION -> ACTIVE с подтверждением коэффициента.",
    responses={
        403: {"description": "Недостаточно прав или событие создано модератором"},
        404: {"description": "Событие не найдено"},
        409: {"description": "Событие не на модерации"},
    },
)
async def approve_event(
    event_id: int,
    moderator: ModeratorUser,
    db: DbSession,
    payload: ApproveEventRequest | None = None,
) -> EventRead:
    """Одобряет событие."""
    event = await moderation_service.approve_event(
        db,
        event_id,
        moderator,
        payload.fixed_coefficient if payload else None,
    )
    return await _event_read(db, event)


@router.post(
    "/events/{event_id}/reject",
    response_model=EventRead,
    summary="Отклонить событие",
    description="PENDING_MODERATION -> REJECTED. Причина сохраняется в событии.",
    responses={
        403: {"description": "Недостаточно прав или событие создано модератором"},
        404: {"description": "Событие не найдено"},
        409: {"description": "Событие не на модерации"},
    },
)
async def reject_event(
    event_id: int,
    payload: RejectEventRequest,
    moderator: ModeratorUser,
    db: DbSession,
) -> EventRead:
    """Отклоняет событие."""
    event = await moderation_service.reject_event(db, event_id, moderator, payload.reason)
    return await _event_read(db, event)


@router.post(
    "/events/{event_id}/resolve",
    response_model=EventRead,
    summary="Зафиксировать исход",
    description=(
        "ACTIVE -> CLOSED. Ставки YES на победный вариант и NO на остальные "
        "получают выплату `amount * coefficient` (округление половина вверх)."
    ),
    responses={
        403: {"description": "Недостаточно прав или событие создано модератором"},
        404: {"description": "Событие не найдено"},
        409: {"description": "Событие не активно или уже рассчитано"},
        422: {"description": "Вариант не принадлежит событию"},
    },
)
async def resolve_event(
    event_id: int,
    payload: ResolveEventRequest,
    moderator: ModeratorUser,
    db: DbSession,
) -> EventRead:
    """Фиксирует победный вариант и начисляет выплаты."""
    event = await moderation_service.resolve_event(
        db,
        event_id,
        moderator,
        payload.winning_option_id,
    )
    return await _event_read(db, event)


@router.post(
    "/events/{event_id}/cancel",
    response_model=EventRead,
    summary="Отменить событие",
    description="ACTIVE/PENDING_MODERATION -> CANCELLED с возвратом баллов.",
    responses={
        403: {"description": "Недостаточно прав или событие создано модератором"},
        404: {"description": "Событие не найдено"},
        409: {"description": "Событие уже закрыто или отменено"},
    },
)
async def cancel_event(
    event_id: int,
    moderator: ModeratorUser,
    db: DbSession,
) -> EventRead:
    """Отменяет событие и возвращает баллы."""
    event = await moderation_service.cancel_event(db, event_id, moderator)
    return await _event_read(db, event)


@router.get(
    "/complaints",
    response_model=Page[ComplaintRead],
    summary="Все жалобы",
    description="Список жалоб с фильтром по статусу.",
    responses={403: {"description": "Недостаточно прав"}},
)
async def list_complaints(
    _: ModeratorUser,
    db: DbSession,
    complaint_status: Annotated[
        ComplaintStatus | None,
        Query(alias="status", description="Фильтр по статусу жалобы"),
    ] = None,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[ComplaintRead]:
    """Возвращает жалобы для модерации."""
    conditions = []
    if complaint_status is not None:
        conditions.append(Complaint.status == complaint_status)

    total = await db.scalar(select(func.count(Complaint.id)).where(*conditions)) or 0
    complaints = list(
        (
            await db.scalars(
                select(Complaint)
                .where(*conditions)
                .order_by(Complaint.created_at.desc(), Complaint.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )

    return Page[ComplaintRead](
        items=[ComplaintRead.model_validate(complaint) for complaint in complaints],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/complaints/{complaint_id}/resolve",
    response_model=ComplaintRead,
    summary="Обработать жалобу",
    description="Переводит жалобу в RESOLVED или REJECTED.",
    responses={
        403: {"description": "Недостаточно прав"},
        404: {"description": "Жалоба не найдена"},
        409: {"description": "Жалоба уже обработана"},
    },
)
async def resolve_complaint(
    complaint_id: int,
    payload: ComplaintResolveRequest,
    moderator: ModeratorUser,
    db: DbSession,
) -> ComplaintRead:
    """Обрабатывает жалобу."""
    complaint = await moderation_service.resolve_complaint(
        db,
        complaint_id,
        moderator,
        payload.status,
        payload.resolution_comment,
    )
    return ComplaintRead.model_validate(complaint)
