"""Модель журнала модерации событий."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ModerationAction
from app.database import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class ModerationLog(Base):
    """Запись о действии модератора над событием."""

    __tablename__ = "moderation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    moderator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[ModerationAction] = mapped_column(
        SAEnum(ModerationAction, native_enum=False, length=20, name="moderation_action"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    event: Mapped[Event] = relationship(lazy="selectin")
    moderator: Mapped[User | None] = relationship(lazy="selectin")
