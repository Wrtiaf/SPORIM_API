"""Жалобы пользователей на события."""

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.core.enums import ComplaintStatus
from app.core.exceptions import ConflictError
from app.dependencies import CurrentUser, DbSession, LimitParam, OffsetParam
from app.models.complaint import Complaint
from app.schemas.common import Page
from app.schemas.complaint import ComplaintCreate, ComplaintRead
from app.services.event_service import get_event_or_404

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post(
    "",
    response_model=ComplaintRead,
    status_code=status.HTTP_201_CREATED,
    summary="Подать жалобу",
    description=(
        "Создаёт жалобу на событие. Один пользователь может иметь только "
        "одну необработанную жалобу на событие."
    ),
    responses={
        401: {"description": "Требуется авторизация"},
        404: {"description": "Событие не найдено"},
        409: {"description": "Уже есть необработанная жалоба на это событие"},
    },
)
async def create_complaint(
    payload: ComplaintCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ComplaintRead:
    """Создаёт жалобу на событие."""
    await get_event_or_404(db, payload.event_id)

    existing = await db.scalar(
        select(Complaint.id).where(
            Complaint.reporter_id == current_user.id,
            Complaint.event_id == payload.event_id,
            Complaint.status == ComplaintStatus.PENDING,
        )
    )
    if existing is not None:
        raise ConflictError(
            "У вас уже есть необработанная жалоба на это событие",
            code="complaint_already_exists",
        )

    complaint = Complaint(
        reporter_id=current_user.id,
        event_id=payload.event_id,
        reason=payload.reason,
        status=ComplaintStatus.PENDING,
    )
    db.add(complaint)
    await db.commit()
    await db.refresh(complaint)
    return ComplaintRead.model_validate(complaint)


@router.get(
    "/my",
    response_model=Page[ComplaintRead],
    summary="Мои жалобы",
)
async def list_my_complaints(
    current_user: CurrentUser,
    db: DbSession,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[ComplaintRead]:
    """Возвращает жалобы текущего пользователя."""
    conditions = [Complaint.reporter_id == current_user.id]

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
