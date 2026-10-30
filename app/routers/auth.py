"""Аутентификация: регистрация, вход, обновление токенов, выход."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import UnauthorizedError
from app.core.security import blacklist_token
from app.dependencies import CurrentUser, DbSession, bearer_scheme
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация",
    description=(
        "Создаёт пользователя с ролью USER, стартовым балансом "
        "(DEFAULT_BALANCE) и сразу возвращает пару JWT-токенов."
    ),
    responses={409: {"description": "username или email уже заняты"}},
)
async def register(payload: RegisterRequest, db: DbSession) -> TokenPair:
    """Регистрирует пользователя и выдаёт токены."""
    user = await auth_service.register_user(db, payload)
    return auth_service.build_token_pair(user)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Вход",
    description="Аутентификация по email или username. Возвращает access и refresh токены.",
    responses={401: {"description": "Неверный логин или пароль"}},
)
async def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    """Аутентифицирует пользователя и выдаёт токены."""
    user = await auth_service.authenticate_user(db, payload.identifier, payload.password)
    return auth_service.build_token_pair(user)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Обновление токенов",
    description=(
        "Принимает refresh-токен, отзывает его (rotation) и возвращает новую "
        "пару токенов."
    ),
    responses={401: {"description": "Токен недействителен или отозван"}},
)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    """Обновляет access-токен по refresh-токену."""
    return await auth_service.refresh_token_pair(db, payload.refresh_token)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Выход",
    description=(
        "Добавляет текущий access-токен в чёрный список. Если в теле передан "
        "refresh_token, он также отзывается. Чёрный список хранится в памяти "
        "процесса (MVP)."
    ),
    responses={401: {"description": "Требуется авторизация"}},
)
async def logout(
    current_user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    payload: LogoutRequest | None = None,
) -> MessageResponse:
    """Отзывает текущий access-токен (и опционально refresh-токен)."""
    if credentials is None:
        raise UnauthorizedError("Требуется авторизация", code="not_authenticated")

    blacklist_token(credentials.credentials)
    if payload is not None and payload.refresh_token:
        blacklist_token(payload.refresh_token)

    return MessageResponse(message=f"Пользователь {current_user.username} вышел из системы")
