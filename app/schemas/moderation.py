"""Схемы модерации событий и жалоб."""

from pydantic import BaseModel, Field, field_validator

from app.core.enums import ComplaintStatus


class ResolveEventRequest(BaseModel):
    """Фиксация победного варианта события."""

    winning_option_id: int = Field(gt=0)


class RejectEventRequest(BaseModel):
    """Отклонение события с указанием причины."""

    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Причина должна содержать минимум 3 символа")
        return stripped


class ComplaintResolveRequest(BaseModel):
    """Обработка жалобы модератором."""

    status: ComplaintStatus = Field(description="RESOLVED или REJECTED")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: ComplaintStatus) -> ComplaintStatus:
        if value is ComplaintStatus.PENDING:
            raise ValueError("Жалобу можно перевести только в RESOLVED или REJECTED")
        return value
