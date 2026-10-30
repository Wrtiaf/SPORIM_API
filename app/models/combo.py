"""Модели комбо-ставок."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ComboStatus
from app.database import Base

if TYPE_CHECKING:
    from app.models.bet import Bet
    from app.models.user import User


class Combo(Base):
    """Комбо — объединение нескольких ставок пользователя.

    Комбо не создаёт отдельного денежного обязательства: выплаты начисляются
    по каждой входящей ставке при фиксации исхода. Комбо отражает
    произведение коэффициентов и агрегированный статус.
    """

    __tablename__ = "combos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_coefficient: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        server_default=text("1.0"),
    )
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

    user: Mapped[User] = relationship(back_populates="combos")
    bets: Mapped[list[Bet]] = relationship(
        secondary="combo_bets",
        back_populates="combos",
        lazy="selectin",
        order_by="Bet.id",
    )

    def __repr__(self) -> str:
        return (
            f"<Combo id={self.id} user={self.user_id} "
            f"coefficient={self.total_coefficient} status={self.status.value}>"
        )


class ComboBet(Base):
    """Связующая таблица many-to-many Combo ↔ Bet.

    Ставка может входить не более чем в одно комбо (уникальный `bet_id`),
    что исключает двойной учёт одной ставки.
    """

    __tablename__ = "combo_bets"

    combo_id: Mapped[int] = mapped_column(
        ForeignKey("combos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bet_id: Mapped[int] = mapped_column(
        ForeignKey("bets.id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,
    )
