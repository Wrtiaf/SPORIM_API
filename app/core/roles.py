"""Ролевая модель платформы."""

from enum import Enum


class Role(str, Enum):
    """Роль пользователя.

    Роли упорядочены по уровню доступа: USER < MODERATOR < ADMIN.
    """

    USER = "USER"
    MODERATOR = "MODERATOR"
    ADMIN = "ADMIN"


ROLE_RANK: dict[Role, int] = {
    Role.USER: 0,
    Role.MODERATOR: 1,
    Role.ADMIN: 2,
}


def has_role_at_least(user_role: Role, required: Role) -> bool:
    """Проверяет, что роль пользователя не ниже требуемой.

    Args:
        user_role: роль пользователя.
        required: минимально необходимая роль.

    Returns:
        True, если уровень доступа достаточен.
    """
    return ROLE_RANK[user_role] >= ROLE_RANK[required]
