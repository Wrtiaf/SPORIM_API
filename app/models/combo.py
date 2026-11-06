"""Модели комбинированных позиций."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BetChoice, ComboLegResult, ComboSide, ComboStatus
from app.database import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.option import Option
    from app.models.user import User


class Combo(Base):
    """Комбинированная позиция из нескольких ног."""

    __tablename__ = "combos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    side: Mapped[ComboSide] = mapped_column(
        SAEnum(ComboSide, native_enum=False, length=10, name="combo_side"),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    potential_payout: Mapped[int] = mapped_column(Integer, nullable=False)
    payout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ComboStatus] = mapped_column(
        SAEnum(ComboStatus, native_enum=False, length=20, name="combo_status"),
        nullable=False,
        default=ComboStatus.ACTIVE,
        server_default=ComboStatus.ACTIVE.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="combos")
    legs: Mapped[list[ComboLeg]] = relationship(
        back_populates="combo",
        cascade="all, delete-orphan",
        order_by="ComboLeg.id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Combo id={self.id} user={self.user_id} side={self.side.value} "
            f"amount={self.amount} status={self.status.value}>"
        )


class ComboLeg(Base):
    """Нога комбинированной позиции."""

    __tablename__ = "combo_legs"
    __table_args__ = (
        UniqueConstraint("combo_id", "event_id", name="uq_combo_legs_combo_id_event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    combo_id: Mapped[int] = mapped_column(
        ForeignKey("combos.id", ondelete="CASCADE"),
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
        SAEnum(BetChoice, native_enum=False, length=10, name="combo_leg_choice"),
        nullable=False,
    )
    coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    result: Mapped[ComboLegResult] = mapped_column(
        SAEnum(ComboLegResult, native_enum=False, length=20, name="combo_leg_result"),
        nullable=False,
        default=ComboLegResult.PENDING,
        server_default=ComboLegResult.PENDING.value,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    combo: Mapped[Combo] = relationship(back_populates="legs")
    event: Mapped[Event] = relationship(lazy="selectin")
    option: Mapped[Option] = relationship(lazy="selectin")
