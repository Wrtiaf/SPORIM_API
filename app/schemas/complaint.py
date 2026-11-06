"""Схемы жалоб."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import ComplaintStatus
from app.schemas.common import ORMModel
from app.schemas.event import EventShort
from app.schemas.user import UserShort


class ComplaintCreate(BaseModel):
    """Создание жалобы на событие."""

    event_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Причина должна содержать минимум 3 символа")
        return stripped


class ComplaintRead(ORMModel):
    """Жалоба с краткой информацией о событии и авторе."""

    id: int
    reporter_id: int
    reporter: UserShort
    event_id: int
    event: EventShort
    reason: str
    status: ComplaintStatus
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: int | None
    resolution_comment: str | None
