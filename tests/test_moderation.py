"""Тесты модерации, жалоб и администрирования."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sqlalchemy import select

from app.core.enums import ModerationAction
from app.core.roles import Role
from app.models.moderation_log import ModerationLog
from tests.helpers import (
    PASSWORD,
    approve_event,
    auth_headers,
    create_category,
    create_event,
    register_user,
    set_role,
)


async def setup_users(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Создаёт автора, модератора и категорию."""
    creator = await register_user(client, "creator")
    moderator = await register_user(client, "moderator")
    await set_role(session_factory, moderator["user"]["id"], Role.MODERATOR)
    category_id = await create_category(session_factory)
    return creator, moderator, category_id


async def test_pending_events_and_approve(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)
    moderator_headers = auth_headers(moderator["access_token"])

    pending = await client.get("/moderation/events/pending", headers=moderator_headers)
    assert pending.status_code == 200
    assert pending.json()["total"] == 1

    forbidden = await client.get(
        "/moderation/events/pending",
        headers=auth_headers(creator["access_token"]),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "insufficient_role"

    approved = await client.post(
        f"/moderation/events/{event['id']}/approve",
        headers=moderator_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "ACTIVE"

    repeated = await client.post(
        f"/moderation/events/{event['id']}/approve",
        headers=moderator_headers,
    )
    assert repeated.status_code == 409


async def test_approve_with_coefficient_and_audit_log(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)

    approved = await client.post(
        f"/moderation/events/{event['id']}/approve",
        headers=auth_headers(moderator["access_token"]),
        json={"fixed_coefficient": 3.25},
    )
    assert approved.status_code == 200
    assert approved.json()["fixed_coefficient"] == 3.25
    assert approved.json()["approved_by"] == moderator["user"]["id"]
    assert approved.json()["approved_at"] is not None

    async with session_factory() as session:
        logs = list((await session.scalars(select(ModerationLog))).all())
    assert len(logs) == 1
    assert logs[0].action is ModerationAction.APPROVE
    assert logs[0].moderator_id == moderator["user"]["id"]


async def test_moderator_cannot_moderate_own_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(moderator["access_token"]), category_id)
    headers = auth_headers(moderator["access_token"])

    approve = await client.post(f"/moderation/events/{event['id']}/approve", headers=headers)
    assert approve.status_code == 403
    assert approve.json()["code"] == "self_moderation_forbidden"

    reject = await client.post(
        f"/moderation/events/{event['id']}/reject",
        headers=headers,
        json={"reason": "Своё событие"},
    )
    assert reject.status_code == 403


async def test_reject_pending_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)

    response = await client.post(
        f"/moderation/events/{event['id']}/reject",
        headers=auth_headers(moderator["access_token"]),
        json={"reason": "Нарушает правила платформы"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert response.json()["rejection_reason"] == "Нарушает правила платформы"


async def test_resolve_rejects_foreign_option(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event_a = await create_event(client, auth_headers(creator["access_token"]), category_id)
    event_b = await create_event(
        client,
        auth_headers(creator["access_token"]),
        category_id,
        title="Другое событие",
    )
    moderator_headers = auth_headers(moderator["access_token"])
    await approve_event(client, moderator_headers, event_a["id"])

    response = await client.post(
        f"/moderation/events/{event_a['id']}/resolve",
        headers=moderator_headers,
        json={"winning_option_id": event_b["options"][0]["id"]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_winning_option"


async def test_complaints_flow(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)
    moderator_headers = auth_headers(moderator["access_token"])
    await approve_event(client, moderator_headers, event["id"])

    reporter = await register_user(client, "reporter")
    reporter_headers = auth_headers(reporter["access_token"])

    created = await client.post(
        "/complaints",
        headers=reporter_headers,
        json={"event_id": event["id"], "reason": "Некорректные варианты исхода"},
    )
    assert created.status_code == 201
    complaint = created.json()
    assert complaint["status"] == "PENDING"

    duplicate = await client.post(
        "/complaints",
        headers=reporter_headers,
        json={"event_id": event["id"], "reason": "Повторная жалоба"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "complaint_already_exists"

    my = await client.get("/complaints/my", headers=reporter_headers)
    assert my.json()["total"] == 1

    listed = await client.get(
        "/moderation/complaints",
        headers=moderator_headers,
        params={"status": "PENDING"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    resolved = await client.post(
        f"/moderation/complaints/{complaint['id']}/resolve",
        headers=moderator_headers,
        json={"status": "RESOLVED"},
    )
    assert resolved.status_code == 200
    payload = resolved.json()
    assert payload["status"] == "RESOLVED"
    assert payload["resolved_at"] is not None
    assert payload["resolved_by"] == moderator["user"]["id"]
    assert payload["resolution_comment"] is None

    repeated = await client.post(
        f"/moderation/complaints/{complaint['id']}/resolve",
        headers=moderator_headers,
        json={"status": "REJECTED"},
    )
    assert repeated.status_code == 409


async def test_admin_roles_ban_and_stats(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    admin = await register_user(client, "admin")
    await set_role(session_factory, admin["user"]["id"], Role.ADMIN)
    admin_headers = auth_headers(admin["access_token"])

    user = await register_user(client, "user")
    user_id = user["user"]["id"]
    user_headers = auth_headers(user["access_token"])

    users = await client.get("/admin/users", headers=admin_headers)
    assert users.status_code == 200
    assert users.json()["total"] >= 2

    promoted = await client.put(
        f"/admin/users/{user_id}/role",
        headers=admin_headers,
        json={"role": "MODERATOR"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "MODERATOR"

    # Повышенный пользователь теперь имеет доступ к модерации.
    pending = await client.get("/moderation/events/pending", headers=user_headers)
    assert pending.status_code == 200

    # Но не к админке.
    forbidden = await client.get("/admin/users", headers=user_headers)
    assert forbidden.status_code == 403

    cannot_make_admin = await client.put(
        f"/admin/users/{user_id}/role",
        headers=admin_headers,
        json={"role": "ADMIN"},
    )
    assert cannot_make_admin.status_code == 422
    assert cannot_make_admin.json()["code"] == "cannot_assign_admin_role"

    self_change = await client.put(
        f"/admin/users/{admin['user']['id']}/role",
        headers=admin_headers,
        json={"role": "MODERATOR"},
    )
    assert self_change.status_code == 400

    banned = await client.put(
        f"/admin/users/{user_id}/ban",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert banned.status_code == 200
    assert banned.json()["is_active"] is False

    blocked_request = await client.get("/users/me", headers=user_headers)
    assert blocked_request.status_code == 403
    assert blocked_request.json()["code"] == "user_inactive"

    blocked_login = await client.post(
        "/auth/login",
        json={"identifier": "user", "password": PASSWORD},
    )
    assert blocked_login.status_code == 403

    unban = await client.put(
        f"/admin/users/{user_id}/ban",
        headers=admin_headers,
        json={"is_active": True},
    )
    assert unban.status_code == 200

    category = await client.post(
        "/admin/categories",
        headers=admin_headers,
        json={"name": "Спорт", "slug": "sport"},
    )
    assert category.status_code == 201

    stats = await client.get("/admin/stats", headers=admin_headers)
    assert stats.status_code == 200
    payload = stats.json()
    assert payload["users_total"] >= 2
    assert payload["admins"] >= 1
    assert payload["moderators"] >= 1
    assert payload["categories_total"] == 1


async def test_admin_category_crud(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    admin = await register_user(client, "admin")
    await set_role(session_factory, admin["user"]["id"], Role.ADMIN)
    admin_headers = auth_headers(admin["access_token"])
    creator = await register_user(client, "creator")

    created = await client.post(
        "/admin/categories",
        headers=admin_headers,
        json={"name": "Криптовалюта", "slug": "crypto"},
    )
    assert created.status_code == 201
    category = created.json()

    duplicate = await client.post(
        "/admin/categories",
        headers=admin_headers,
        json={"name": "Крипта", "slug": "crypto"},
    )
    assert duplicate.status_code == 409

    updated = await client.put(
        f"/admin/categories/{category['id']}",
        headers=admin_headers,
        json={"name": "Крипто-активы"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Крипто-активы"

    event = await create_event(
        client,
        auth_headers(creator["access_token"]),
        category["id"],
    )
    assert event["category_id"] == category["id"]

    in_use = await client.delete(
        f"/admin/categories/{category['id']}",
        headers=admin_headers,
    )
    assert in_use.status_code == 409
    assert in_use.json()["code"] == "category_has_events"

    empty = await client.post(
        "/admin/categories",
        headers=admin_headers,
        json={"name": "Пустая", "slug": "empty"},
    )
    deleted = await client.delete(
        f"/admin/categories/{empty.json()['id']}",
        headers=admin_headers,
    )
    assert deleted.status_code == 200
