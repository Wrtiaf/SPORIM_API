"""SQLAlchemy-модели «СПОРИМ».

Модуль импортирует все модели, чтобы Alembic и `Base.metadata`
видели полную схему.
"""

from app.models.bet import Bet
from app.models.category import Category
from app.models.combo import Combo, ComboLeg
from app.models.complaint import Complaint
from app.models.event import Event
from app.models.moderation_log import ModerationLog
from app.models.option import Option
from app.models.user import User

__all__ = [
    "Bet",
    "Category",
    "Combo",
    "ComboLeg",
    "Complaint",
    "Event",
    "ModerationLog",
    "Option",
    "User",
]
