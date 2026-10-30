"""Хеширование паролей, выпуск и проверка JWT, чёрный список токенов."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory чёрный список отозванных токенов: jti -> момент истечения.
# Для MVP этого достаточно; при горизонтальном масштабировании заменить на Redis.
_blacklist: dict[str, datetime] = {}
_blacklist_lock = Lock()


def hash_password(password: str) -> str:
    """Хеширует пароль алгоритмом bcrypt.

    Args:
        password: пароль в открытом виде.

    Returns:
        bcrypt-хеш пароля.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет пароль против bcrypt-хеша.

    Args:
        plain_password: введённый пароль.
        hashed_password: сохранённый хеш.

    Returns:
        True, если пароль верный.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Повреждённый или несовместимый хеш не должен ронять запрос.
        logger.warning("Не удалось проверить хеш пароля")
        return False


def _create_token(user_id: int, token_type: str, expires_delta: timedelta) -> str:
    """Создаёт подписанный JWT.

    Args:
        user_id: идентификатор пользователя (claim `sub`).
        token_type: тип токена — `access` или `refresh`.
        expires_delta: срок жизни токена.

    Returns:
        Строка JWT.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int) -> str:
    """Создаёт access-токен."""
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    """Создаёт refresh-токен."""
    return _create_token(
        user_id,
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Декодирует и валидирует JWT.

    Args:
        token: строка токена.
        expected_type: ожидаемый тип (`access`/`refresh`); если задан,
            тип из payload должен совпадать.

    Returns:
        Payload токена.

    Raises:
        UnauthorizedError: если токен недействителен, истёк или имеет
            неверный тип.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise UnauthorizedError(
            "Недействительный или истёкший токен",
            code="invalid_token",
        ) from exc

    if expected_type is not None and payload.get("type") != expected_type:
        raise UnauthorizedError(
            f"Ожидался {expected_type}-токен",
            code="invalid_token_type",
        )
    return payload


def blacklist_token(token: str) -> None:
    """Добавляет токен в чёрный список до момента его истечения.

    Args:
        token: JWT, который нужно отозвать.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError as exc:
        raise UnauthorizedError("Недействительный токен", code="invalid_token") from exc

    jti = payload.get("jti")
    if not jti:
        raise UnauthorizedError("В токене отсутствует jti", code="invalid_token")

    exp = payload.get("exp")
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc)
        if isinstance(exp, int | float)
        else datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )

    with _blacklist_lock:
        _cleanup_blacklist()
        _blacklist[jti] = expires_at


def is_token_blacklisted(jti: str | None) -> bool:
    """Проверяет, отозван ли токен."""
    if not jti:
        return False
    with _blacklist_lock:
        expires_at = _blacklist.get(jti)
        if expires_at is None:
            return False
        if expires_at <= datetime.now(timezone.utc):
            _blacklist.pop(jti, None)
            return False
        return True


def _cleanup_blacklist() -> None:
    """Удаляет истёкшие записи чёрного списка (вызывается под блокировкой)."""
    now = datetime.now(timezone.utc)
    expired = [jti for jti, expires_at in _blacklist.items() if expires_at <= now]
    for jti in expired:
        _blacklist.pop(jti, None)


def access_token_expires_in() -> int:
    """Возвращает время жизни access-токена в секундах."""
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
