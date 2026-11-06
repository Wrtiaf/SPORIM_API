"""Тесты ставок: баланс, проценты, выплаты, отмена и идемпотентность."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.money import calculate_payout
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


async def prepare_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    options: tuple[str, ...] = ("Да", "Нет"),
    coefficient: float = 2.0,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Создаёт автора, модератора и одобренное событие."""
    creator = await register_user(client, "creator")
    moderator = await register_user(client, "moderator")
    await set_role(session_factory, moderator["user"]["id"], Role.MODERATOR)

    category_id = await create_category(session_factory)
    event = await create_event(
        client,
        auth_headers(creator["access_token"]),
        category_id,
        options=options,
        coefficient=coefficient,
    )
    approved = await approve_event(
        client,
        auth_headers(moderator["access_token"]),
        event["id"],
    )
    return creator, moderator, approved


@pytest.mark.parametrize(
    ("amount", "coefficient", "expected"),
    [
        (10, 2.0, 20),
        (15, 1.5, 23),
        (1, 1.1, 1),
        (3, 1.5, 5),
        (7, 2.25, 16),
        (0, 2.0, 0),
    ],
)
def test_calculate_payout_rounding(amount: int, coefficient: float, expected: int) -> None:
    """Выплата округляется до целого по правилу «половина вверх»."""
    assert calculate_payout(amount, coefficient) == expected


async def test_event_options_have_zero_percent_without_votes(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, _, event = await prepare_event(client, session_factory, options=("A", "B", "C"))

    response = await client.get(f"/events/{event['id']}/options")
    assert response.status_code == 200
    assert [option["current_percentage"] for option in response.json()] == [0.0, 0.0, 0.0]


async def test_place_bet_deducts_balance_and_fixes_coefficient(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, _, event = await prepare_event(client, session_factory, coefficient=2.0)
    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    option_id = event["options"][0]["id"]

    bet = await place_bet(client, headers, option_id, choice="YES", amount=100)

    assert bet["amount"] == 100
    assert bet["coefficient"] == 2.0
    assert bet["status"] == "PENDING"
    assert bet["potential_payout"] == 200
    assert bet["event"]["id"] == event["id"]
    assert bet["option"]["id"] == option_id
    assert await get_balance(client, headers) == 900

    stats = await client.get("/users/me/stats", headers=headers)
    assert stats.json()["total_bets"] == 1
    assert stats.json()["pending_bets"] == 1
    assert stats.json()["total_staked"] == 100

    options = (await client.get(f"/events/{event['id']}/options")).json()
    assert options[0]["yes_count"] == 1
    assert options[0]["no_count"] == 0
    assert options[0]["current_percentage"] == 100.0
    assert options[1]["current_percentage"] == 0.0

    details = (await client.get(f"/events/{event['id']}")).json()
    assert details["volume"] == 100


async def test_second_bet_on_same_event_is_rejected(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, _, event = await prepare_event(client, session_factory)
    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])
    option_id = event["options"][0]["id"]

    await place_bet(client, headers, option_id, amount=100)

    response = await client.post(
        f"/options/{option_id}/bet",
        headers=headers,
        json={"choice": "NO", "amount": 50},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "bet_already_exists"
    assert await get_balance(client, headers) == 900


async def test_bet_on_pending_event_is_rejected(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator = await register_user(client, "creator")
    category_id = await create_category(session_factory)
    event = await create_event(client, auth_headers(creator["access_token"]), category_id)
    bettor = await register_user(client, "bettor")

    response = await client.post(
        f"/options/{event['options'][0]['id']}/bet",
        headers=auth_headers(bettor["access_token"]),
        json={"choice": "YES", "amount": 10},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "event_not_active"


async def test_bet_with_insufficient_balance_is_rejected(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, _, event = await prepare_event(client, session_factory)
    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])

    response = await client.post(
        f"/options/{event['options'][0]['id']}/bet",
        headers=headers,
        json={"choice": "YES", "amount": 2000},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_balance"
    assert await get_balance(client, headers) == 1000


async def test_bet_on_own_event_is_rejected(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    creator, _, event = await prepare_event(client, session_factory)

    response = await client.post(
        f"/options/{event['options'][0]['id']}/bet",
        headers=auth_headers(creator["access_token"]),
        json={"choice": "YES", "amount": 10},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "own_event_bet"
    assert await get_balance(client, auth_headers(creator["access_token"])) == 1000


async def test_foreign_bet_is_hidden(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, _, event = await prepare_event(client, session_factory)
    owner = await register_user(client, "owner")
    stranger = await register_user(client, "stranger")

    bet = await place_bet(
        client,
        auth_headers(owner["access_token"]),
        event["options"][0]["id"],
        amount=10,
    )

    response = await client.get(
        f"/bets/{bet['id']}",
        headers=auth_headers(stranger["access_token"]),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "bet_not_found"


async def test_percentages_are_calculated_per_option(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Проценты независимы: yes / (yes + no) внутри варианта."""
    _, _, event = await prepare_event(client, session_factory, options=("A", "B", "C"))
    first, second, third = event["options"]

    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    carol = await register_user(client, "carol")

    await place_bet(client, auth_headers(alice["access_token"]), first["id"], "YES", 10)
    await place_bet(client, auth_headers(bob["access_token"]), first["id"], "NO", 10)
    await place_bet(client, auth_headers(carol["access_token"]), second["id"], "YES", 10)

    options = (await client.get(f"/events/{event['id']}/options")).json()
    percentages = {option["id"]: option["current_percentage"] for option in options}

    assert percentages[first["id"]] == 50.0
    assert percentages[second["id"]] == 100.0
    assert percentages[third["id"]] == 0.0
    # Проценты вариантов — независимые рынки, их сумма не обязана быть 100.
    assert sum(percentages.values()) == 150.0


async def test_resolve_pays_winners_and_marks_losers(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, moderator, event = await prepare_event(client, session_factory)
    yes_user = await register_user(client, "yes_user")
    no_user = await register_user(client, "no_user")
    yes_headers = auth_headers(yes_user["access_token"])
    no_headers = auth_headers(no_user["access_token"])
    winning_option = event["options"][0]["id"]

    yes_bet = await place_bet(client, yes_headers, winning_option, "YES", 100)
    no_bet = await place_bet(client, no_headers, winning_option, "NO", 100)

    response = await client.post(
        f"/moderation/events/{event['id']}/resolve",
        headers=auth_headers(moderator["access_token"]),
        json={"winning_option_id": winning_option},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CLOSED"

    assert await get_balance(client, yes_headers) == 1100
    assert await get_balance(client, no_headers) == 900

    yes_after = (await client.get(f"/bets/{yes_bet['id']}", headers=yes_headers)).json()
    no_after = (await client.get(f"/bets/{no_bet['id']}", headers=no_headers)).json()
    assert yes_after["status"] == "WON"
    assert no_after["status"] == "LOST"

    stats = (await client.get("/users/me/stats", headers=yes_headers)).json()
    assert stats["won_bets"] == 1
    assert stats["win_rate"] == 100.0
    assert stats["total_won"] == 200

    # Повторная фиксация исхода не должна начислять выплаты ещё раз.
    repeated = await client.post(
        f"/moderation/events/{event['id']}/resolve",
        headers=auth_headers(moderator["access_token"]),
        json={"winning_option_id": winning_option},
    )
    assert repeated.status_code == 409
    assert await get_balance(client, yes_headers) == 1100


async def test_no_bet_wins_when_another_option_wins(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ставка NO выигрывает, если победил другой вариант."""
    _, moderator, event = await prepare_event(client, session_factory, options=("A", "B"))
    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])

    first_option, second_option = event["options"]
    await place_bet(client, headers, first_option["id"], "NO", 100)

    response = await client.post(
        f"/moderation/events/{event['id']}/resolve",
        headers=auth_headers(moderator["access_token"]),
        json={"winning_option_id": second_option["id"]},
    )
    assert response.status_code == 200
    assert await get_balance(client, headers) == 1100


async def test_cancel_event_refunds_pending_bets(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, moderator, event = await prepare_event(client, session_factory)
    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])

    bet = await place_bet(client, headers, event["options"][0]["id"], "YES", 150)
    assert await get_balance(client, headers) == 850

    response = await client.post(
        f"/moderation/events/{event['id']}/cancel",
        headers=auth_headers(moderator["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert await get_balance(client, headers) == 1000

    bet_after = (await client.get(f"/bets/{bet['id']}", headers=headers)).json()
    assert bet_after["status"] == "REFUNDED"

    repeated = await client.post(
        f"/moderation/events/{event['id']}/cancel",
        headers=auth_headers(moderator["access_token"]),
    )
    assert repeated.status_code == 409
    assert await get_balance(client, headers) == 1000


async def test_payout_rounding_end_to_end(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, moderator, event = await prepare_event(client, session_factory, coefficient=1.5)
    bettor = await register_user(client, "bettor")
    headers = auth_headers(bettor["access_token"])

    bet = await place_bet(client, headers, event["options"][0]["id"], "YES", 15)
    assert bet["potential_payout"] == 23

    await client.post(
        f"/moderation/events/{event['id']}/resolve",
        headers=auth_headers(moderator["access_token"]),
        json={"winning_option_id": event["options"][0]["id"]},
    )
    assert await get_balance(client, headers) == 1000 - 15 + 23
