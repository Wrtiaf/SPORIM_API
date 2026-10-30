"""Категории событий."""

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import DbSession
from app.models.category import Category
from app.schemas.category import CategoryRead

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get(
    "",
    response_model=list[CategoryRead],
    summary="Список категорий",
    description="Возвращает все категории, отсортированные по названию.",
)
async def list_categories(db: DbSession) -> list[CategoryRead]:
    """Возвращает список категорий."""
    categories = (await db.scalars(select(Category).order_by(Category.name))).all()
    return [CategoryRead.model_validate(category) for category in categories]
