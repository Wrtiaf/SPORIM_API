"""Модель ставки."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BetChoice, BetStatus
from app.core.money import calculate_payout
from app.database import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.option import Option
    from app.models.user import User


class Bet(Base):
    """Ставка пользователя на вариант события.

    Один пользователь может сделать только одну ставку на событие —
    это гарантируется уникальным ограничением `(user_id, event_id)`.
    """

    __tablename__ = "bets"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_bets_user_id_event_id"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("options.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    choice: Mapped[BetChoice] = mapped_column(
        SAEnum(BetChoice, native_enum=False, length=10, name="bet_choice"),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[BetStatus] = mapped_column(
        SAEnum(BetStatus, native_enum=False, length=20, name="bet_status"),
        nullable=False,
        default=BetStatus.PENDING,
        server_default=BetStatus.PENDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    user: Mapped[User] = relationship(back_populates="bets")
    event: Mapped[Event] = relationship(back_populates="bets", lazy="selectin")
    option: Mapped[Option] = relationship(back_populates="bets", lazy="selectin")

    @property
    def potential_payout(self) -> int:
        """Потенциальная выплата при выигрыше (целые баллы)."""
        return calculate_payout(self.amount, self.coefficient)

    def __repr__(self) -> str:
        return (
            f"<Bet id={self.id} user={self.user_id} event={self.event_id} "
            f"choice={self.choice.value} amount={self.amount} status={self.status.value}>"
        )
