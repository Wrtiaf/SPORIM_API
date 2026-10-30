"""Административные операции (только ADMIN)."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import BetStatus, ComplaintStatus, EventStatus
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.core.roles import Role
from app.dependencies import AdminUser, DbSession, LimitParam, OffsetParam
from app.models.bet import Bet
from app.models.category import Category
from app.models.complaint import Complaint
from app.models.event import Event
from app.models.user import User
from app.schemas.admin import AdminUserUpdate, BanRequest, PlatformStats
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import MessageResponse, Page
from app.schemas.user import UserRead

router = APIRouter(prefix="/admin", tags=["Admin"])


async def _count(db: AsyncSession, model: type, *conditions: object) -> int:
    """Считает строки модели с условиями."""
    value = await db.scalar(select(func.count()).select_from(model).where(*conditions))
    return int(value or 0)


async def _sum(db: AsyncSession, expression: object, *conditions: object) -> int:
    """Суммирует SQL-выражение с условиями."""
    value = await db.scalar(select(func.coalesce(func.sum(expression), 0)).where(*conditions))
    return int(value or 0)


@router.get(
    "/users",
    response_model=Page[UserRead],
    summary="Все пользователи",
    description="Пагинация с фильтрами по роли, активности и подстроке username/email.",
    responses={403: {"description": "Недостаточно прав"}},
)
async def list_users(
    _: AdminUser,
    db: DbSession,
    role: Annotated[Role | None, Query(description="Фильтр по роли")] = None,
    is_active: Annotated[bool | None, Query(description="Фильтр по активности")] = None,
    search: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> Page[UserRead]:
    """Возвращает список пользователей."""
    conditions = []
    if role is not None:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(or_(User.username.ilike(pattern), User.email.ilike(pattern)))

    total = await _count(db, User, *conditions)
    users = list(
        (
            await db.scalars(
                select(User)
                .where(*conditions)
                .order_by(User.created_at.desc(), User.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )

    return Page[UserRead](
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put(
    "/users/{user_id}/role",
    response_model=UserRead,
    summary="Назначить роль",
    description=(
        "Позволяет назначить USER или MODERATOR. Роль ADMIN через этот "
        "эндпоинт не выдаётся и не снимается; менять свою роль нельзя."
    ),
    responses={
        400: {"description": "Попытка изменить собственную роль"},
        403: {"description": "Недостаточно прав или целевой пользователь — ADMIN"},
        404: {"description": "Пользователь не найден"},
    },
)
async def update_user_role(
    user_id: int,
    payload: AdminUserUpdate,
    admin: AdminUser,
    db: DbSession,
) -> UserRead:
    """Меняет роль пользователя."""
    if user_id == admin.id:
        raise BadRequestError("Нельзя изменить собственную роль", code="cannot_change_own_role")

    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден", code="user_not_found")
    if user.role is Role.ADMIN:
        raise ForbiddenError("Нельзя изменить роль администратора", code="cannot_change_admin_role")
    if payload.role is Role.ADMIN:
        raise ValidationAppError(
            "Роль ADMIN через этот эндпоинт не выдаётся",
            code="cannot_assign_admin_role",
        )

    user.role = payload.role
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.put(
    "/users/{user_id}/ban",
    response_model=UserRead,
    summary="Забанить/разбанить",
    description="Меняет `is_active`. Заблокированный пользователь не может войти и ставить.",
    responses={
        400: {"description": "Попытка заблокировать себя"},
        403: {"description": "Недостаточно прав или целевой пользователь — ADMIN"},
        404: {"description": "Пользователь не найден"},
    },
)
async def ban_user(
    user_id: int,
    payload: BanRequest,
    admin: AdminUser,
    db: DbSession,
) -> UserRead:
    """Блокирует или разблокирует пользователя."""
    if user_id == admin.id:
        raise BadRequestError("Нельзя заблокировать себя", code="cannot_ban_self")

    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден", code="user_not_found")
    if user.role is Role.ADMIN:
        raise ForbiddenError("Нельзя заблокировать администратора", code="cannot_ban_admin")

    user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.get(
    "/stats",
    response_model=PlatformStats,
    summary="Статистика платформы",
    description="Агрегированные показатели по пользователям, событиям и ставкам.",
    responses={403: {"description": "Недостаточно прав"}},
)
async def platform_stats(_: AdminUser, db: DbSession) -> PlatformStats:
    """Возвращает общую статистику платформы."""
    return PlatformStats(
        users_total=await _count(db, User),
        users_active=await _count(db, User, User.is_active.is_(True)),
        moderators=await _count(db, User, User.role == Role.MODERATOR),
        admins=await _count(db, User, User.role == Role.ADMIN),
        categories_total=await _count(db, Category),
        events_total=await _count(db, Event),
        events_pending=await _count(db, Event, Event.status == EventStatus.PENDING_MODERATION),
        events_active=await _count(db, Event, Event.status == EventStatus.ACTIVE),
        events_closed=await _count(db, Event, Event.status == EventStatus.CLOSED),
        events_cancelled=await _count(db, Event, Event.status == EventStatus.CANCELLED),
        bets_total=await _count(db, Bet),
        bets_pending=await _count(db, Bet, Bet.status == BetStatus.PENDING),
        bets_won=await _count(db, Bet, Bet.status == BetStatus.WON),
        bets_lost=await _count(db, Bet, Bet.status == BetStatus.LOST),
        bets_refunded=await _count(db, Bet, Bet.status == BetStatus.REFUNDED),
        points_staked_total=await _sum(db, Bet.amount),
        points_pending=await _sum(db, Bet.amount, Bet.status == BetStatus.PENDING),
        points_refunded=await _sum(db, Bet.amount, Bet.status == BetStatus.REFUNDED),
        points_paid_out_gross=await _sum(
            db,
            Bet.amount * Bet.coefficient,
            Bet.status == BetStatus.WON,
        ),
        complaints_total=await _count(db, Complaint),
        complaints_pending=await _count(db, Complaint, Complaint.status == ComplaintStatus.PENDING),
    )


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать категорию",
    responses={
        403: {"description": "Недостаточно прав"},
        409: {"description": "Категория с таким name или slug уже существует"},
    },
)
async def create_category(
    payload: CategoryCreate,
    _: AdminUser,
    db: DbSession,
) -> CategoryRead:
    """Создаёт категорию."""
    category = Category(name=payload.name, slug=payload.slug)
    db.add(category)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "Категория с таким name или slug уже существует",
            code="category_already_exists",
        ) from exc

    await db.refresh(category)
    return CategoryRead.model_validate(category)


@router.put(
    "/categories/{category_id}",
    response_model=CategoryRead,
    summary="Редактировать категорию",
    responses={
        403: {"description": "Недостаточно прав"},
        404: {"description": "Категория не найдена"},
        409: {"description": "Категория с таким name или slug уже существует"},
    },
)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    _: AdminUser,
    db: DbSession,
) -> CategoryRead:
    """Обновляет категорию."""
    category = await db.get(Category, category_id)
    if category is None:
        raise NotFoundError("Категория не найдена", code="category_not_found")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(category, field, value)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "Категория с таким name или slug уже существует",
            code="category_already_exists",
        ) from exc

    await db.refresh(category)
    return CategoryRead.model_validate(category)


@router.delete(
    "/categories/{category_id}",
    response_model=MessageResponse,
    summary="Удалить категорию",
    description="Удаление запрещено, если к категории привязаны события.",
    responses={
        403: {"description": "Недостаточно прав"},
        404: {"description": "Категория не найдена"},
        409: {"description": "В категории есть события"},
    },
)
async def delete_category(
    category_id: int,
    _: AdminUser,
    db: DbSession,
) -> MessageResponse:
    """Удаляет пустую категорию."""
    category = await db.get(Category, category_id)
    if category is None:
        raise NotFoundError("Категория не найдена", code="category_not_found")

    events_count = await _count(db, Event, Event.category_id == category_id)
    if events_count > 0:
        raise ConflictError(
            "Нельзя удалить категорию, к которой привязаны события",
            code="category_has_events",
        )

    await db.delete(category)
    await db.commit()
    return MessageResponse(message=f"Категория {category_id} удалена")
