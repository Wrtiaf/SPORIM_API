"""Модель события (спора)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EventStatus
from app.database import Base

if TYPE_CHECKING:
    from app.models.bet import Bet
    from app.models.category import Category
    from app.models.option import Option
    from app.models.user import User


class Event(Base):
    """Событие, на исход которого пользователи делают прогнозы."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[EventStatus] = mapped_column(
        SAEnum(EventStatus, native_enum=False, length=30, name="event_status"),
        nullable=False,
        default=EventStatus.PENDING_MODERATION,
        server_default=EventStatus.PENDING_MODERATION.value,
        index=True,
    )
    resolution_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fixed_coefficient: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=2.0,
        server_default=text("2.0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    category: Mapped[Category] = relationship(back_populates="events", lazy="selectin")
    creator: Mapped[User] = relationship(
        back_populates="created_events",
        foreign_keys=[creator_id],
        lazy="selectin",
    )
    resolver: Mapped[User | None] = relationship(foreign_keys=[resolved_by], lazy="selectin")
    options: Mapped[list[Option]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="Option.id",
        lazy="selectin",
    )
    bets: Mapped[list[Bet]] = relationship(back_populates="event")

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r} status={self.status.value}>"
