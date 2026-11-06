"""Тесты видимости событий, поиска, soft delete и валидации."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.roles import Role
from tests.helpers import (
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
    creator = await register_user(client, "creator")
    moderator = await register_user(client, "moderator")
    await set_role(session_factory, moderator["user"]["id"], Role.MODERATOR)
    category_id = await create_category(session_factory)
    return creator, moderator, category_id


async def test_pending_event_is_hidden_from_strangers(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)

    stranger = await register_user(client, "stranger")
    hidden = await client.get(
        f"/events/{event['id']}",
        headers=auth_headers(stranger["access_token"]),
    )
    assert hidden.status_code == 404

    hidden_options = await client.get(
        f"/events/{event['id']}/options",
        headers=auth_headers(stranger["access_token"]),
    )
    assert hidden_options.status_code == 404

    own = await client.get(f"/events/{event['id']}", headers=auth_headers(creator["access_token"]))
    assert own.status_code == 200

    moderator_view = await client.get(
        f"/events/{event['id']}",
        headers=auth_headers(moderator["access_token"]),
    )
    assert moderator_view.status_code == 200

    anonymous = await client.get(f"/events/{event['id']}")
    assert anonymous.status_code == 404


async def test_rejected_event_is_visible_to_author(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)

    rejected = await client.post(
        f"/moderation/events/{event['id']}/reject",
        headers=auth_headers(moderator["access_token"]),
        json={"reason": "Недостаточно данных"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    own = await client.get(f"/events/{event['id']}", headers=auth_headers(creator["access_token"]))
    assert own.status_code == 200
    assert own.json()["rejection_reason"] == "Недостаточно данных"

    stranger = await register_user(client, "stranger")
    hidden = await client.get(
        f"/events/{event['id']}",
        headers=auth_headers(stranger["access_token"]),
    )
    assert hidden.status_code == 404


async def test_rejected_event_can_be_resubmitted(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)
    creator_headers = auth_headers(creator["access_token"])

    await client.post(
        f"/moderation/events/{event['id']}/reject",
        headers=auth_headers(moderator["access_token"]),
        json={"reason": "Плохое описание"},
    )

    updated = await client.put(
        f"/events/{event['id']}",
        headers=creator_headers,
        json={"description": "Исправленное описание"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "PENDING_MODERATION"
    assert updated.json()["rejection_reason"] is None


async def test_resolve_returns_winner(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)
    moderator_headers = auth_headers(moderator["access_token"])
    await approve_event(client, moderator_headers, event["id"])
    winner = event["options"][1]

    resolved = await client.post(
        f"/moderation/events/{event['id']}/resolve",
        headers=moderator_headers,
        json={"winning_option_id": winner["id"]},
    )
    assert resolved.status_code == 200
    payload = resolved.json()
    assert payload["status"] == "CLOSED"
    assert payload["winning_option_id"] == winner["id"]
    assert payload["winner"]["id"] == winner["id"]
    assert payload["resolved_by"] == moderator["user"]["id"]


async def test_soft_delete_hides_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, _, category_id = await setup_users(client, session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)
    headers = auth_headers(creator["access_token"])

    deleted = await client.delete(f"/events/{event['id']}", headers=headers)
    assert deleted.status_code == 200

    hidden = await client.get(f"/events/{event['id']}", headers=headers)
    assert hidden.status_code == 404

    repeated = await client.delete(f"/events/{event['id']}", headers=headers)
    assert repeated.status_code == 404

    pending = await client.get("/moderation/events/pending", headers=headers)
    assert pending.status_code == 403


async def test_create_event_validates_urls(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator = await register_user(client, "creator")
    category_id = await create_category(session_factory)

    response = await client.post(
        "/events",
        headers=auth_headers(creator["access_token"]),
        json={
            "title": "Событие с плохой ссылкой",
            "category_id": category_id,
            "image_url": "javascript:alert(1)",
            "options": [{"title": "Да"}, {"title": "Нет"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_create_event_validates_coefficient_range(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator = await register_user(client, "creator")
    category_id = await create_category(session_factory)

    for coefficient in (1.0, 10.01):
        response = await client.post(
            "/events",
            headers=auth_headers(creator["access_token"]),
            json={
                "title": "Событие с плохим коэффициентом",
                "category_id": category_id,
                "fixed_coefficient": coefficient,
                "options": [{"title": "Да"}, {"title": "Нет"}],
            },
        )
        assert response.status_code == 422


async def test_search_escapes_like_wildcards(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_users(client, session_factory)
    percent_event = await create_event(
        client,
        auth_headers(creator["access_token"]),
        category_id,
        title="Событие 100%",
    )
    other_event = await create_event(
        client,
        auth_headers(creator["access_token"]),
        category_id,
        title="Событие 100 баллов",
    )
    moderator_headers = auth_headers(moderator["access_token"])
    await approve_event(client, moderator_headers, percent_event["id"])
    await approve_event(client, moderator_headers, other_event["id"])

    found = await client.get("/search", params={"q": "100%"})
    assert found.status_code == 200
    assert [item["id"] for item in found.json()["items"]] == [percent_event["id"]]

    too_short = await client.get("/search", params={"q": " a "})
    assert too_short.status_code == 422
    assert too_short.json()["code"] == "search_query_too_short"
