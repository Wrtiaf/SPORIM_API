"""Схемы аутентификации."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    """Данные регистрации."""

    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("username", mode="before")
    @classmethod
    def _strip_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def _check_bcrypt_limit(cls, value: str) -> str:
        # bcrypt учитывает только первые 72 байта пароля.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Пароль не должен превышать 72 байта")
        return value


class LoginRequest(BaseModel):
    """Данные входа: email или username + пароль."""

    identifier: str = Field(min_length=3, max_length=255, description="Email или username")
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    """Запрос обновления access-токена."""

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """Необязательное тело выхода: позволяет отозвать refresh-токен."""

    refresh_token: str | None = None


class TokenData(BaseModel):
    """Декодированные данные JWT."""

    sub: int | None = None
    token_type: str | None = None
    jti: str | None = None


class TokenPair(BaseModel):
    """Пара токенов и профиль пользователя."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Время жизни access-токена в секундах")
    user: UserRead
