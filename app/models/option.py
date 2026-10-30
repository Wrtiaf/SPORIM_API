"""Модель варианта исхода события."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.bet import Bet
    from app.models.event import Event


class Option(Base):
    """Вариант исхода события.

    `yes_count` — количество ставок «Да» на этот вариант,
    `no_count` — количество ставок «Нет» на этот вариант.
    `current_percentage` — доля «Да» среди всех голосов по варианту (0..100).
    """

    __tablename__ = "options"
    __table_args__ = (
        UniqueConstraint("event_id", "title", name="uq_options_event_id_title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    yes_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    no_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    current_percentage: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default=text("0"),
    )

    event: Mapped[Event] = relationship(back_populates="options")
    bets: Mapped[list[Bet]] = relationship(back_populates="option")

    @property
    def total_votes(self) -> int:
        """Общее количество голосов по варианту."""
        return self.yes_count + self.no_count

    def __repr__(self) -> str:
        return f"<Option id={self.id} title={self.title!r} yes={self.yes_count} no={self.no_count}>"
