"""Комбо-ставки."""

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DbSession, LimitParam, OffsetParam
from app.models.combo import Combo
from app.schemas.combo import ComboCreate, ComboRead
from app.schemas.common import Page
from app.services import combo_service

router = APIRouter(prefix="/combos", tags=["Combos"])


@router.post(
    "",
    response_model=ComboRead,
    status_code=status.HTTP_201_CREATED,
    summary="Собрать комбо",
    description=(
        "Создаёт комбо из PENDING-ставок пользователя. `total_coefficient` — "
        "произведение коэффициентов. Ставка может входить только в одно комбо."
    ),
    responses={
        401: {"description": "Требуется авторизация"},
        404: {"description": "Ставки не найдены"},
        409: {"description": "Ставка уже рассчитана или входит в другое комбо"},
    },
)
async def create_combo(
    payload: ComboCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ComboRead:
    """Создаёт комбо из ставок текущего пользователя."""
    combo = await combo_service.create_combo(db, current_user, payload)
    return ComboRead.model_validate(combo)


@router.get(
    "",
    response_model=Page[ComboRead],
    summary="Мои комбо",
)
async def list_my_combos(
    current_user: CurrentUser,
    db: DbSession,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[ComboRead]:
    """Возвращает комбо текущего пользователя."""
    conditions = [Combo.user_id == current_user.id]

    total = await db.scalar(select(func.count(Combo.id)).where(*conditions)) or 0
    combos = list(
        (
            await db.scalars(
                select(Combo)
                .where(*conditions)
                .order_by(Combo.created_at.desc(), Combo.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )

    return Page[ComboRead](
        items=[ComboRead.model_validate(combo) for combo in combos],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{combo_id}",
    response_model=ComboRead,
    summary="Детали комбо",
    description="Комбо с входящими ставками и текущим статусом.",
    responses={
        403: {"description": "Нет доступа к чужому комбо"},
        404: {"description": "Комбо не найдено"},
    },
)
async def get_combo(combo_id: int, current_user: CurrentUser, db: DbSession) -> ComboRead:
    """Возвращает детали комбо."""
    combo = await combo_service.get_combo_or_404(db, combo_id, current_user)
    return ComboRead.model_validate(combo)
