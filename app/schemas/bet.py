"""Схемы ставок."""

from datetime import datetime

from pydantic import Field

from app.core.enums import BetChoice, BetStatus
from app.schemas.common import ORMModel
from app.schemas.event import EventShort
from app.schemas.option import OptionRead


class BetRead(ORMModel):
    """Ставка пользователя."""

    id: int
    user_id: int
    event_id: int
    option_id: int
    choice: BetChoice
    amount: int
    coefficient: float
    status: BetStatus
    created_at: datetime
    potential_payout: int = Field(description="Выплата при выигрыше в целых баллах")
    event: EventShort
    option: OptionRead
