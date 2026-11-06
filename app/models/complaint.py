"""Модель жалобы на событие."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ComplaintStatus
from app.database import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class Complaint(Base):
    """Жалоба пользователя на событие."""

    __tablename__ = "complaints"
    __table_args__ = (
        Index(
            "uq_complaints_pending_reporter_event",
            "reporter_id",
            "event_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
            sqlite_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ComplaintStatus] = mapped_column(
        SAEnum(ComplaintStatus, native_enum=False, length=20, name="complaint_status"),
        nullable=False,
        default=ComplaintStatus.PENDING,
        server_default=ComplaintStatus.PENDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    reporter: Mapped[User] = relationship(
        back_populates="complaints",
        foreign_keys=[reporter_id],
        lazy="selectin",
    )
    resolver: Mapped[User | None] = relationship(foreign_keys=[resolved_by], lazy="selectin")
    event: Mapped[Event] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<Complaint id={self.id} event={self.event_id} status={self.status.value}>"
