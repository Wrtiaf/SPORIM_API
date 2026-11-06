"""Поиск событий."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.core.enums import EventStatus
from app.core.exceptions import ValidationAppError
from app.dependencies import DbSession, LimitParam, OffsetParam
from app.models.event import Event
from app.schemas.common import Page
from app.schemas.event import EventRead
from app.services.event_service import build_event_reads

router = APIRouter(prefix="/search", tags=["Search"])


def _escape_like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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
    q: Annotated[str, Query(max_length=100, description="Поисковый запрос")],
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[EventRead]:
    """Ищет события по названию и описанию."""
    query = q.strip()
    if len(query) < 2:
        raise ValidationAppError(
            "Поисковый запрос должен содержать минимум 2 символа",
            code="search_query_too_short",
        )

    pattern = _escape_like(query)
    conditions = [
        Event.status == EventStatus.ACTIVE,
        Event.deleted_at.is_(None),
        or_(
            Event.title.ilike(pattern, escape="\\"),
            Event.description.ilike(pattern, escape="\\"),
        ),
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
