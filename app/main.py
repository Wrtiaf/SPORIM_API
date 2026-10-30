"""Точка входа FastAPI-приложения «СПОРИМ»."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.database import engine
from app.routers import (
    admin,
    auth,
    bets,
    categories,
    combos,
    complaints,
    events,
    moderation,
    search,
    users,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Управляет жизненным циклом приложения."""
    logger.info("Запуск %s v%s (%s)", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    yield
    await engine.dispose()
    logger.info("Приложение остановлено")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "MVP API платформы прогнозов «СПОРИМ».\n\n"
        "Все пари заключаются на виртуальные баллы. Пользователи создают события, "
        "модераторы вручную фиксируют исходы.\n\n"
        "Роли: USER, MODERATOR, ADMIN. Авторизация — Bearer JWT "
        "(access + refresh)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.get("/health", tags=["System"], summary="Проверка работоспособности")
async def health() -> dict[str, str]:
    """Возвращает статус сервиса."""
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["System"], summary="Корень API", include_in_schema=False)
async def root() -> dict[str, str]:
    """Возвращает ссылку на документацию."""
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(events.router)
app.include_router(bets.router)
app.include_router(combos.router)
app.include_router(search.router)
app.include_router(complaints.router)
app.include_router(moderation.router)
app.include_router(admin.router)
