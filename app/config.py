"""Конфигурация приложения, загружаемая из переменных окружения и `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения.

    Значения по умолчанию рассчитаны на локальную разработку. В production
    все секреты и строки подключения должны задаваться через переменные
    окружения (см. `.env.example`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Общие настройки
    APP_NAME: str = "СПОРИМ API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SQL_ECHO: bool = False

    # База данных
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sporim"

    # JWT
    SECRET_KEY: str = "dev-insecure-secret-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS (фронтенд Vite)
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Экономика
    DEFAULT_BALANCE: int = 1000

    @property
    def cors_origins(self) -> list[str]:
        """Возвращает список origin'ов для CORS."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()


settings = get_settings()
