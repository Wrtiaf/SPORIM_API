"""Тесты комбо: коэффициент, статусы, возвраты и отсутствие двойных выплат."""

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
    place_bet,
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
) -> dict[str, Any]:
    """Создаёт и одобряет событие."""
    event = await create_event(
        client,
        auth_headers(creator["access_token"]),
        category_id,
        title=title,
    )
    return await approve_event(
        client,
        auth_headers(moderator["access_token"]),
        event["id"],
    )


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


async def test_combo_coefficient_and_win_without_double_payout(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])

    bet_a = await place_bet(client, headers, event_a["options"][0]["id"], "YES", 100)
    bet_b = await place_bet(client, headers, event_b["options"][0]["id"], "YES", 100)

    combo_response = await client.post(
        "/combos",
        headers=headers,
        json={"bet_ids": [bet_a["id"], bet_b["id"]]},
    )
    assert combo_response.status_code == 201, combo_response.text
    combo = combo_response.json()
    assert combo["total_coefficient"] == 4.0
    assert combo["status"] == "ACTIVE"
    assert len(combo["bets"]) == 2

    # Ставка не может входить во второе комбо.
    duplicate = await client.post(
        "/combos",
        headers=headers,
        json={"bet_ids": [bet_a["id"]]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "bet_already_in_combo"

    await resolve_event(client, moderator, event_a["id"], event_a["options"][0]["id"])
    still_active = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert still_active["status"] == "ACTIVE"

    await resolve_event(client, moderator, event_b["id"], event_b["options"][0]["id"])
    won = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert won["status"] == "WON"
    assert won["total_coefficient"] == 4.0

    # Выплаты начислены только по ставкам: 1000 - 100 - 100 + 200 + 200.
    assert await get_balance(client, headers) == 1200

    repeated = await client.post(
        f"/moderation/events/{event_b['id']}/resolve",
        headers=auth_headers(moderator["access_token"]),
        json={"winning_option_id": event_b["options"][0]["id"]},
    )
    assert repeated.status_code == 409
    assert await get_balance(client, headers) == 1200


async def test_combo_lost_when_any_leg_lost(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    bet_a = await place_bet(client, headers, event_a["options"][0]["id"], "YES", 100)
    bet_b = await place_bet(client, headers, event_b["options"][0]["id"], "YES", 100)

    combo = (
        await client.post(
            "/combos",
            headers=headers,
            json={"bet_ids": [bet_a["id"], bet_b["id"]]},
        )
    ).json()

    await resolve_event(client, moderator, event_a["id"], event_a["options"][1]["id"])
    lost = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert lost["status"] == "LOST"

    await resolve_event(client, moderator, event_b["id"], event_b["options"][0]["id"])
    still_lost = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert still_lost["status"] == "LOST"

    # 1000 - 100 - 100 + 200 (вторая ставка выиграла).
    assert await get_balance(client, headers) == 1000


async def test_combo_excludes_refunded_leg(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    bet_a = await place_bet(client, headers, event_a["options"][0]["id"], "YES", 100)
    bet_b = await place_bet(client, headers, event_b["options"][0]["id"], "YES", 100)

    combo = (
        await client.post(
            "/combos",
            headers=headers,
            json={"bet_ids": [bet_a["id"], bet_b["id"]]},
        )
    ).json()
    assert combo["total_coefficient"] == 4.0

    cancel = await client.post(
        f"/moderation/events/{event_a['id']}/cancel",
        headers=auth_headers(moderator["access_token"]),
    )
    assert cancel.status_code == 200

    after_cancel = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert after_cancel["status"] == "ACTIVE"
    assert after_cancel["total_coefficient"] == 2.0

    await resolve_event(client, moderator, event_b["id"], event_b["options"][0]["id"])
    won = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert won["status"] == "WON"
    assert won["total_coefficient"] == 2.0

    # Возврат 100 по отменённой ставке и выплата 200 по выигравшей.
    assert await get_balance(client, headers) == 1100


async def test_combo_with_all_legs_refunded_is_void(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Если все ставки возвращены, комбо не выигрывает и не проигрывает."""
    creator, moderator, category_id = await setup_base(client, session_factory)
    event_a = await make_event(client, creator, moderator, category_id, "Событие A")
    event_b = await make_event(client, creator, moderator, category_id, "Событие B")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    bet_a = await place_bet(client, headers, event_a["options"][0]["id"], "YES", 100)
    bet_b = await place_bet(client, headers, event_b["options"][0]["id"], "YES", 100)

    combo = (
        await client.post(
            "/combos",
            headers=headers,
            json={"bet_ids": [bet_a["id"], bet_b["id"]]},
        )
    ).json()

    for event in (event_a, event_b):
        response = await client.post(
            f"/moderation/events/{event['id']}/cancel",
            headers=auth_headers(moderator["access_token"]),
        )
        assert response.status_code == 200

    after = (await client.get(f"/combos/{combo['id']}", headers=headers)).json()
    assert after["status"] == "ACTIVE"
    assert after["total_coefficient"] == 1.0
    assert await get_balance(client, headers) == 1000


async def test_combo_cannot_include_resolved_bet(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event = await make_event(client, creator, moderator, category_id, "Событие A")

    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    bet = await place_bet(client, headers, event["options"][0]["id"], "YES", 100)

    await resolve_event(client, moderator, event["id"], event["options"][0]["id"])

    response = await client.post("/combos", headers=headers, json={"bet_ids": [bet["id"]]})
    assert response.status_code == 409
    assert response.json()["code"] == "bet_not_pending"


async def test_combo_cannot_include_foreign_bet(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, moderator, category_id = await setup_base(client, session_factory)
    event = await make_event(client, creator, moderator, category_id, "Событие A")

    owner = await register_user(client, "owner")
    stranger = await register_user(client, "stranger")
    bet = await place_bet(
        client,
        auth_headers(owner["access_token"]),
        event["options"][0]["id"],
        "YES",
        100,
    )

    response = await client.post(
        "/combos",
        headers=auth_headers(stranger["access_token"]),
        json={"bet_ids": [bet["id"]]},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "bet_not_found"
