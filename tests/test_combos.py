"""Тесты комбинированных позиций: коэффициент, сторона, выплаты и отмена ног."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.roles import Role
from tests.helpers import (
    approve_event,
    auth_headers,
    create_category,
    create_event,
    get_balance,
    register_user,
    set_role,
)


async def setup_base(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Создаёт автора, модератора и категорию."""
    creator = await register_user(client, "creator")
    moderator = await register_user(client, "moderator")
    await set_role(session_factory, moderator["user"]["id"], Role.MODERATOR)
    category_id = await create_category(session_factory)
    return creator, moderator, category_id


async def make_event(
    client: AsyncClient,
    creator: dict[str, Any],
    moderator: dict[str, Any],
    category_id: int,
    title: str,
    coefficient: float = 2.0,
) -> dict[str, Any]:
    """Создаёт и одобряет событие."""
    event = await create_event(
        client,
        auth_headers(creator["access_token"]),
        category_id,
        title=title,
        coefficient=coefficient,
    )
    return await approve_event(
        client,
        auth_headers(moderator["access_token"]),
        event["id"],
    )


async def create_combo(
    client: AsyncClient,
    headers: dict[str, str],
    legs: list[tuple[int, str]],
    side: str = "YES",
    amount: int = 100,
) -> dict[str, Any]:
    """Создаёт комбо через API."""
    response = await client.post(
        "/combos",
        headers=headers,
        json={
            "side": side,
            "amount": amount,
            "legs": [{"option_id": option_id, "choice": choice} for option_id, choice in legs],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def resolve_event(
    client: AsyncClient,
    moderator: dict[str, Any],
    event_id: int,
    winning_option_id: int,
) -> None:
    """Фиксирует исход события."""
    response = await client.post(
        f"/moderation/events/{event_id}/resolve",
        headers=auth_headers(moderator["access_token"]),
        json={"winning_option_id": winning_option_id},
    )
    assert response.status_code == 200, response.text


async def test_combo_yes_pays_product(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    combo = await create_combo(
        client,
        headers,
        [(event_a["options"][0]["id"], "YES"), (event_b["options"][0]["id"], "YES")],
    )

    assert combo["side"] == "YES"
    assert combo["amount"] == 100
    assert combo["entry_coefficient"] == 4.0
    assert combo["potential_payout"] == 400
    assert combo["status"] == "ACTIVE"
    assert len(combo["legs"]) == 2
    assert await get_balance(client, headers) == 900

    await resolve_event(client, moderator, event_a["id"], event_a["options"][0]["id"])
    active = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert active["status"] == "ACTIVE"

    await resolve_event(client, moderator, event_b["id"], event_b["options"][0]["id"])
    settled = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert settled["status"] == "SETTLED"
    assert settled["payout"] == 400
    assert all(leg["result"] == "WON" for leg in settled["legs"])
    assert await get_balance(client, headers) == 1300


async def test_combo_yes_loses_when_any_leg_loses(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    combo = await create_combo(
        client,
        headers,
        [(event_a["options"][0]["id"], "YES"), (event_b["options"][0]["id"], "YES")],
    )

    await resolve_event(client, moderator, event_a["id"], event_a["options"][1]["id"])
    await resolve_event(client, moderator, event_b["id"], event_b["options"][0]["id"])

    settled = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert settled["status"] == "SETTLED"
    assert settled["payout"] == 0
    assert await get_balance(client, headers) == 900


async def test_combo_no_pays_complement(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    combo = await create_combo(
        client,
        headers,
        [(event_a["options"][0]["id"], "YES"), (event_b["options"][0]["id"], "YES")],
        side="NO",
    )

    assert combo["entry_coefficient"] == 1.333333
    assert combo["potential_payout"] == 133
    assert await get_balance(client, headers) == 900

    await resolve_event(client, moderator, event_a["id"], event_a["options"][1]["id"])
    await resolve_event(client, moderator, event_b["id"], event_b["options"][0]["id"])

    settled = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert settled["status"] == "SETTLED"
    assert settled["payout"] == 133
    assert await get_balance(client, headers) == 1033


async def test_combo_half_leg_reduces_payout(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    combo = await create_combo(
        client,
        headers,
        [(event_a["options"][0]["id"], "YES"), (event_b["options"][0]["id"], "YES")],
    )

    cancel = await client.post(
        f"/moderation/events/{event_a['id']}/cancel",
        headers=auth_headers(moderator["access_token"]),
    )
    assert cancel.status_code == 200

    active = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert active["status"] == "ACTIVE"
    assert active["legs"][0]["result"] == "HALF"

    await resolve_event(client, moderator, event_b["id"], event_b["options"][0]["id"])
    settled = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert settled["payout"] == 200
    assert await get_balance(client, headers) == 1100


async def test_combo_rejects_duplicate_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event = await make_event(client, creator, moderator, category_id, "Событие A")

    bettor = await register_user(client, "bettor")
    response = await client.post(
        "/combos",
        headers=auth_headers(bettor["access_token"]),
        json={
            "side": "YES",
            "amount": 100,
            "legs": [
                {"option_id": event["options"][0]["id"], "choice": "YES"},
                {"option_id": event["options"][1]["id"], "choice": "YES"},
            ],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_combo_event"


async def test_combo_rejects_own_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    response = await client.post(
        "/combos",
        headers=auth_headers(creator["access_token"]),
        json={
            "side": "YES",
            "amount": 100,
            "legs": [
                {"option_id": event_a["options"][0]["id"], "choice": "YES"},
                {"option_id": event_b["options"][0]["id"], "choice": "YES"},
            ],
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "own_event_combo"


async def test_combo_rejects_insufficient_balance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    response = await client.post(
        "/combos",
        headers=auth_headers(bettor["access_token"]),
        json={
            "side": "YES",
            "amount": 2000,
            "legs": [
                {"option_id": event_a["options"][0]["id"], "choice": "YES"},
                {"option_id": event_b["options"][0]["id"], "choice": "YES"},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_balance"
    assert await get_balance(client, auth_headers(bettor["access_token"])) == 1000


async def test_combo_foreign_view_is_hidden(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    owner = await register_user(client, "owner")
    stranger = await register_user(client, "stranger")
    combo = await create_combo(
        client,
        auth_headers(owner["access_token"]),
        [(event_a["options"][0]["id"], "YES"), (event_b["options"][0]["id"], "YES")],
    )

    response = await client.get(
        f"/combos/{combo['id']}",
        headers=auth_headers(stranger["access_token"]),
    )
    assert response.status_code == 404
