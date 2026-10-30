"""Вспомогательные функции для тестов."""

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.roles import Role
from app.models.category import Category
from app.models.user import User

PASSWORD = "secret123"


def auth_headers(token: str) -> dict[str, str]:
    """Формирует заголовок Authorization."""
    return {"Authorization": f"Bearer {token}"}


async def register_user(
    client: AsyncClient,
    username: str,
    email: str | None = None,
    password: str = PASSWORD,
) -> dict:
    """Регистрирует пользователя через API и возвращает ответ."""
    response = await client.post(
        "/auth/register",
        json={
            "username": username,
            "email": email or f"{username}@example.com",
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_category(
    session_factory: async_sessionmaker[AsyncSession],
    name: str = "Спорт",
    slug: str = "sport",
) -> int:
    """Создаёт категорию напрямую в БД."""
    async with session_factory() as session:
        category = Category(name=name, slug=slug)
        session.add(category)
        await session.commit()
        await session.refresh(category)
        return category.id


async def set_role(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    role: Role,
) -> None:
    """Меняет роль пользователя напрямую в БД."""
    async with session_factory() as session:
        await session.execute(update(User).where(User.id == user_id).values(role=role))
        await session.commit()


async def create_event(
    client: AsyncClient,
    headers: dict[str, str],
    category_id: int,
    title: str = "Тестовое событие",
    options: tuple[str, ...] = ("Да", "Нет"),
    coefficient: float = 2.0,
) -> dict:
    """Создаёт событие через API (статус PENDING_MODERATION)."""
    response = await client.post(
        "/events",
        headers=headers,
        json={
            "title": title,
            "description": "Описание тестового события",
            "category_id": category_id,
            "fixed_coefficient": coefficient,
            "options": [{"title": option} for option in options],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def approve_event(
    client: AsyncClient,
    moderator_headers: dict[str, str],
    event_id: int,
) -> dict:
    """Одобряет событие модератором."""
    response = await client.post(
        f"/moderation/events/{event_id}/approve",
        headers=moderator_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def place_bet(
    client: AsyncClient,
    headers: dict[str, str],
    option_id: int,
    choice: str = "YES",
    amount: int = 100,
) -> dict:
    """Делает ставку через API."""
    response = await client.post(
        f"/options/{option_id}/bet",
        headers=headers,
        json={"choice": choice, "amount": amount},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def get_balance(client: AsyncClient, headers: dict[str, str]) -> int:
    """Возвращает баланс пользователя."""
    response = await client.get("/users/me/balance", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["balance"]
