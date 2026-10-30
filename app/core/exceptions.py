"""Кастомные исключения приложения и глобальные обработчики ошибок."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Базовое прикладное исключение.

    Attributes:
        status_code: HTTP-код ответа.
        code: машиночитаемый код ошибки.
        message: человекочитаемое сообщение.
    """

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


class BadRequestError(AppError):
    """Некорректный запрос (400)."""

    status_code = 400
    code = "bad_request"


class UnauthorizedError(AppError):
    """Пользователь не аутентифицирован (401)."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """Недостаточно прав (403)."""

    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    """Объект не найден (404)."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """Конфликт состояния или дублирование (409)."""

    status_code = 409
    code = "conflict"


class ValidationAppError(AppError):
    """Ошибка бизнес-валидации (422)."""

    status_code = 422
    code = "validation_error"


def error_body(detail: str, code: str, errors: Any | None = None) -> dict[str, Any]:
    """Формирует единое тело ответа с ошибкой."""
    body: dict[str, Any] = {"detail": detail, "code": code}
    if errors is not None:
        body["errors"] = errors
    return body


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует глобальные обработчики исключений.

    Args:
        app: экземпляр FastAPI.
    """

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.message, exc.code),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "Ошибка валидации данных",
                "validation_error",
                jsonable_encoder(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(str(exc.detail), "http_error"),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Необработанная ошибка при запросе %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body("Внутренняя ошибка сервера", "internal_error"),
        )
