"""Тесты валидации конфигурации."""

import pytest
from pydantic import ValidationError

from app.config import DEFAULT_SECRET_KEY, Settings


def test_production_requires_secure_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", DEBUG=False, SECRET_KEY=DEFAULT_SECRET_KEY)

    settings = Settings(ENVIRONMENT="production", DEBUG=False, SECRET_KEY="x" * 40)
    assert settings.ENVIRONMENT == "production"


def test_production_forbids_debug() -> None:
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", DEBUG=True, SECRET_KEY="x" * 40)


def test_production_forbids_wildcard_cors() -> None:
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY="x" * 40,
            CORS_ORIGINS="*",
        )


def test_algorithm_is_restricted() -> None:
    with pytest.raises(ValidationError):
        Settings(ALGORITHM="none")

    assert Settings(ALGORITHM="hs512").ALGORITHM == "HS512"
