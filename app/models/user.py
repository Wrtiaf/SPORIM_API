"""Модель пользователя."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import Role
from app.database import Base

if TYPE_CHECKING:
    from app.models.bet import Bet
    from app.models.combo import Combo
    from app.models.complaint import Complaint
    from app.models.event import Event


class User(Base):
    """Пользователь платформы.

    Баланс и статистика хранятся денормализованно ради быстрых ответов API;
    изменения выполняются атомарными SQL-апдейтами.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    balance: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000,
        server_default=text("1000"),
    )
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, native_enum=False, length=20, name="user_role"),
        nullable=False,
        default=Role.USER,
        server_default=Role.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    total_bets: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    won_bets: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    bets: Mapped[list[Bet]] = relationship(back_populates="user")
    combos: Mapped[list[Combo]] = relationship(back_populates="user")
    created_events: Mapped[list[Event]] = relationship(
        back_populates="creator",
        foreign_keys="Event.creator_id",
    )
    complaints: Mapped[list[Complaint]] = relationship(back_populates="reporter")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"
