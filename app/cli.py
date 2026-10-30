"""CLI-команды для обслуживания платформы.

Примеры:
    python -m app.cli create-admin --username admin --email admin@example.com --password secret123
    python -m app.cli seed-categories
"""

import argparse
import asyncio
import logging

from sqlalchemy import func, or_, select

from app.config import settings
from app.core.roles import Role
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.category import Category
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sporim.cli")

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Политика", "politics"),
    ("Спорт", "sport"),
    ("Криптовалюта", "crypto"),
    ("Киберспорт", "esports"),
    ("Климат", "climate"),
    ("Наука и техника", "science"),
    ("Упоминания", "mentions"),
]


async def create_admin(username: str, email: str, password: str) -> None:
    """Создаёт администратора или повышает существующего пользователя."""
    async with AsyncSessionLocal() as db:
        user = await db.scalar(
            select(User).where(
                or_(
                    func.lower(User.email) == email.lower(),
                    func.lower(User.username) == username.lower(),
                )
            )
        )
        if user is None:
            user = User(
                username=username,
                email=email.lower(),
                hashed_password=hash_password(password),
                balance=settings.DEFAULT_BALANCE,
                role=Role.ADMIN,
            )
            db.add(user)
            action = "создан"
        else:
            user.role = Role.ADMIN
            user.is_active = True
            action = "повышен до ADMIN"

        await db.commit()
        logger.info("Пользователь %s %s", username, action)


async def seed_categories() -> None:
    """Добавляет базовые категории, если их ещё нет."""
    async with AsyncSessionLocal() as db:
        created = 0
        for name, slug in DEFAULT_CATEGORIES:
            exists = await db.scalar(select(Category.id).where(Category.slug == slug))
            if exists is None:
                db.add(Category(name=name, slug=slug))
                created += 1
        await db.commit()
        logger.info("Добавлено категорий: %s", created)


def build_parser() -> argparse.ArgumentParser:
    """Собирает парсер аргументов CLI."""
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Обслуживание «СПОРИМ»")
    subparsers = parser.add_subparsers(dest="command", required=True)

    admin_parser = subparsers.add_parser("create-admin", help="Создать администратора")
    admin_parser.add_argument("--username", required=True)
    admin_parser.add_argument("--email", required=True)
    admin_parser.add_argument("--password", required=True)

    subparsers.add_parser("seed-categories", help="Добавить базовые категории")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "create-admin":
        asyncio.run(create_admin(args.username, args.email, args.password))
    elif args.command == "seed-categories":
        asyncio.run(seed_categories())
    else:  # pragma: no cover - argparse не пропустит неизвестную команду
        logger.error("Неизвестная команда: %s", args.command)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
