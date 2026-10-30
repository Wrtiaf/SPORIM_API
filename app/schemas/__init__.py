"""Pydantic-схемы приложения."""

from app.schemas.admin import AdminUserUpdate, BanRequest, PlatformStats
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenData,
    TokenPair,
)
from app.schemas.bet import BetRead
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.combo import ComboCreate, ComboRead
from app.schemas.common import MessageResponse, Page
from app.schemas.complaint import ComplaintCreate, ComplaintRead
from app.schemas.event import EventCreate, EventRead, EventShort, EventUpdate
from app.schemas.moderation import (
    ComplaintResolveRequest,
    RejectEventRequest,
    ResolveEventRequest,
)
from app.schemas.option import BetCreate, OptionCreate, OptionRead
from app.schemas.user import BalanceRead, UserRead, UserShort, UserStats, UserUpdate

__all__ = [
    "AdminUserUpdate",
    "BalanceRead",
    "BanRequest",
    "BetCreate",
    "BetRead",
    "CategoryCreate",
    "CategoryRead",
    "CategoryUpdate",
    "ComboCreate",
    "ComboRead",
    "ComplaintCreate",
    "ComplaintRead",
    "ComplaintResolveRequest",
    "EventCreate",
    "EventRead",
    "EventShort",
    "EventUpdate",
    "LoginRequest",
    "LogoutRequest",
    "MessageResponse",
    "OptionCreate",
    "OptionRead",
    "Page",
    "PlatformStats",
    "RefreshRequest",
    "RegisterRequest",
    "RejectEventRequest",
    "ResolveEventRequest",
    "TokenData",
    "TokenPair",
    "UserRead",
    "UserShort",
    "UserStats",
    "UserUpdate",
]
