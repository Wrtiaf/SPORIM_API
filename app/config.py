"""Конфигурация приложения, загружаемая из переменных окружения и `.env`."""

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-insecure-secret-key-change-me"
ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512"}
LOCAL_ENVIRONMENTS = {"development", "test", "local"}


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
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS (фронтенд Vite)
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Экономика
    DEFAULT_BALANCE: int = 1000
    MAX_PENDING_EVENTS_PER_USER: int = 10
    MAX_PENDING_COMPLAINTS_PER_USER: int = 20

    @field_validator("ALGORITHM")
    @classmethod
    def _validate_algorithm(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ALLOWED_ALGORITHMS:
            raise ValueError("ALGORITHM должен быть одним из HS256, HS384, HS512")
        return normalized

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        environment = self.ENVIRONMENT.lower()
        if environment in LOCAL_ENVIRONMENTS:
            return self
        if self.DEBUG:
            raise ValueError("DEBUG должен быть выключен вне development")
        if self.SECRET_KEY == DEFAULT_SECRET_KEY or len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY должен быть случайным и содержать минимум 32 символа")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS не должен содержать '*' вне development")
        return self

    @property
    def cors_origins(self) -> list[str]:
        """Возвращает список origin'ов для CORS."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()


settings = get_settings()
