"""Регистрация, вход и работа с токенами."""

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.roles import Role
from app.core.security import (
    access_token_expires_in,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_token_blacklisted,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenPair
from app.schemas.user import UserRead

logger = logging.getLogger(__name__)


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    """Создаёт нового пользователя.

    Args:
        db: сессия БД.
        payload: валидированные данные регистрации.

    Returns:
        Созданный пользователь.

    Raises:
        ConflictError: username или email уже заняты.
    """
    username = payload.username.strip()
    email = payload.email.lower()

    existing = await db.scalar(
        select(User.id).where(
            or_(
                func.lower(User.username) == username.lower(),
                User.email == email,
            )
        )
    )
    if existing is not None:
        raise ConflictError(
            "Пользователь с таким username или email уже существует",
            code="user_already_exists",
        )

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(payload.password),
        balance=settings.DEFAULT_BALANCE,
        role=Role.USER,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "Пользователь с таким username или email уже существует",
            code="user_already_exists",
        ) from exc

    await db.refresh(user)
    logger.info("Зарегистрирован пользователь id=%s username=%s", user.id, user.username)
    return user


async def authenticate_user(db: AsyncSession, identifier: str, password: str) -> User:
    """Проверяет учётные данные по email или username.

    Args:
        db: сессия БД.
        identifier: email или username.
        password: пароль в открытом виде.

    Returns:
        Аутентифицированный пользователь.

    Raises:
        UnauthorizedError: неверные учётные данные.
        ForbiddenError: аккаунт заблокирован.
    """
    user = await db.scalar(
        select(User).where(
            or_(
                func.lower(User.email) == identifier.strip().lower(),
                func.lower(User.username) == identifier.strip().lower(),
            )
        )
    )
    if user is None or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Неверный логин или пароль", code="invalid_credentials")
    if not user.is_active:
        raise ForbiddenError("Аккаунт заблокирован", code="user_inactive")
    return user


def build_token_pair(user: User) -> TokenPair:
    """Выпускает пару access/refresh токенов для пользователя."""
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=access_token_expires_in(),
        user=UserRead.model_validate(user),
    )


async def refresh_token_pair(db: AsyncSession, refresh_token: str) -> TokenPair:
    """Обновляет пару токенов и отзывает использованный refresh-токен.

    Args:
        db: сессия БД.
        refresh_token: действующий refresh-токен.

    Returns:
        Новая пара токенов.

    Raises:
        UnauthorizedError: токен недействителен, отозван или пользователь не найден.
        ForbiddenError: аккаунт заблокирован.
    """
    payload = decode_token(refresh_token, expected_type="refresh")
    if is_token_blacklisted(payload.get("jti")):
        raise UnauthorizedError("Refresh-токен отозван", code="token_revoked")

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Некорректный токен", code="invalid_token") from exc

    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден", code="user_not_found")
    if not user.is_active:
        raise ForbiddenError("Аккаунт заблокирован", code="user_inactive")

    blacklist_token(refresh_token)
    return build_token_pair(user)
