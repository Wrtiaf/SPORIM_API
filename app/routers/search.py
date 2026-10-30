"""Поиск событий."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.core.enums import EventStatus
from app.dependencies import DbSession, LimitParam, OffsetParam
from app.models.event import Event
from app.schemas.common import Page
from app.schemas.event import EventRead
from app.services.event_service import build_event_reads

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=Page[EventRead],
    summary="Поиск событий",
    description=(
        "Ищет активные события по title и description (регистронезависимо). "
        "Минимальная длина запроса — 2 символа."
    ),
)
async def search_events(
    db: DbSession,
    q: Annotated[str, Query(min_length=2, max_length=100, description="Поисковый запрос")],
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[EventRead]:
    """Ищет события по названию и описанию."""
    pattern = f"%{q.strip()}%"
    conditions = [
        Event.status == EventStatus.ACTIVE,
        or_(Event.title.ilike(pattern), Event.description.ilike(pattern)),
    ]

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
