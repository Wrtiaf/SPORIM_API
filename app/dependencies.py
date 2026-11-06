"""Зависимости FastAPI: сессия БД, текущий пользователь, роли, пагинация."""

from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.roles import Role
from app.core.security import decode_token, is_token_blacklisted
from app.database import get_db
from app.models.user import User

# HTTPBearer вместо OAuth2PasswordBearer: вход в API выполняется JSON-запросом,
# а не form-data, поэтому стандартный password-flow в Swagger не нужен.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access-токен")

DbSession = Annotated[AsyncSession, Depends(get_db)]

LimitParam = Annotated[int, Query(ge=1, le=100, description="Размер страницы (1..100)")]
OffsetParam = Annotated[int, Query(ge=0, description="Смещение")]

DEFAULT_LIMIT = 20


async def _user_from_credentials(
    db: AsyncSession,
    credentials: HTTPAuthorizationCredentials,
) -> User:
    payload = decode_token(credentials.credentials, expected_type="access")

    if is_token_blacklisted(payload.get("jti")):
        raise UnauthorizedError("Токен отозван", code="token_revoked")

    subject = payload.get("sub")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Некорректный токен", code="invalid_token") from exc

    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден", code="user_not_found")
    if not user.is_active:
        raise ForbiddenError("Аккаунт заблокирован", code="user_inactive")
    return user


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Возвращает текущего пользователя по access-токену.

    Args:
        db: сессия БД.
        credentials: Bearer-токен из заголовка Authorization.

    Returns:
        ORM-объект пользователя.

    Raises:
        UnauthorizedError: токен отсутствует, недействителен или отозван.
        ForbiddenError: аккаунт заблокирован.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Требуется авторизация", code="not_authenticated")
    return await _user_from_credentials(db, credentials)


async def get_current_user_optional(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User | None:
    """Возвращает текущего пользователя или None без токена."""
    if credentials is None or not credentials.credentials:
        return None
    return await _user_from_credentials(db, credentials)


def require_roles(*roles: Role):
    """Фабрика зависимостей, проверяющая роль текущего пользователя.

    Args:
        *roles: роли, которым разрешён доступ.

    Returns:
        Зависимость FastAPI, возвращающая пользователя.
    """

    async def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in roles:
            allowed = ", ".join(role.value for role in roles)
            raise ForbiddenError(
                f"Недостаточно прав. Требуется одна из ролей: {allowed}",
                code="insufficient_role",
            )
        return current_user

    return dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(get_current_user_optional)]
ModeratorUser = Annotated[User, Depends(require_roles(Role.MODERATOR, Role.ADMIN))]
AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
