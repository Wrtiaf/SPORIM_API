"""Тесты регистрации, входа и токенов."""

from httpx import AsyncClient

from tests.helpers import PASSWORD, auth_headers, register_user


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_register_creates_user_with_start_balance(client: AsyncClient) -> None:
    data = await register_user(client, "alice")

    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["username"] == "alice"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["balance"] == 1000
    assert data["user"]["role"] == "USER"
    assert data["user"]["is_active"] is True


async def test_register_duplicate_username(client: AsyncClient) -> None:
    await register_user(client, "alice")

    response = await client.post(
        "/auth/register",
        json={
            "username": "alice",
            "email": "other@example.com",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "user_already_exists"


async def test_username_is_case_insensitive_but_keeps_case(client: AsyncClient) -> None:
    data = await register_user(client, "Alice")
    assert data["user"]["username"] == "Alice"

    duplicate = await client.post(
        "/auth/register",
        json={"username": "alice", "email": "other@example.com", "password": PASSWORD},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "user_already_exists"

    login = await client.post(
        "/auth/login",
        json={"identifier": "ALICE", "password": PASSWORD},
    )
    assert login.status_code == 200


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await register_user(client, "alice")

    response = await client.post(
        "/auth/register",
        json={
            "username": "bob",
            "email": "alice@example.com",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "user_already_exists"


async def test_register_validation(client: AsyncClient) -> None:
    cases = [
        {"username": "ab", "email": "a@example.com", "password": PASSWORD},
        {"username": "alice", "email": "not-an-email", "password": PASSWORD},
        {"username": "alice", "email": "a@example.com", "password": "short"},
        {"username": "алиса", "email": "a@example.com", "password": PASSWORD},
    ]
    for payload in cases:
        response = await client.post("/auth/register", json=payload)
        assert response.status_code == 422, payload
        assert response.json()["code"] == "validation_error"


async def test_login_by_email_and_username(client: AsyncClient) -> None:
    await register_user(client, "alice")

    by_email = await client.post(
        "/auth/login",
        json={"identifier": "alice@example.com", "password": PASSWORD},
    )
    by_username = await client.post(
        "/auth/login",
        json={"identifier": "alice", "password": PASSWORD},
    )

    assert by_email.status_code == 200
    assert by_username.status_code == 200
    assert by_email.json()["user"]["id"] == by_username.json()["user"]["id"]


async def test_login_wrong_password(client: AsyncClient) -> None:
    await register_user(client, "alice")

    response = await client.post(
        "/auth/login",
        json={"identifier": "alice", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


async def test_me_returns_profile(client: AsyncClient) -> None:
    data = await register_user(client, "alice")

    response = await client.get("/users/me", headers=auth_headers(data["access_token"]))
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


async def test_refresh_rotates_token(client: AsyncClient) -> None:
    data = await register_user(client, "alice")

    refreshed = await client.post(
        "/auth/refresh",
        json={"refresh_token": data["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != data["access_token"]

    reused = await client.post(
        "/auth/refresh",
        json={"refresh_token": data["refresh_token"]},
    )
    assert reused.status_code == 401
    assert reused.json()["code"] == "token_revoked"


async def test_logout_revokes_access_token(client: AsyncClient) -> None:
    data = await register_user(client, "alice")
    headers = auth_headers(data["access_token"])

    logout = await client.post(
        "/auth/logout",
        headers=headers,
        json={"refresh_token": data["refresh_token"]},
    )
    assert logout.status_code == 200

    me = await client.get("/users/me", headers=headers)
    assert me.status_code == 401
    assert me.json()["code"] == "token_revoked"

    refresh = await client.post(
        "/auth/refresh",
        json={"refresh_token": data["refresh_token"]},
    )
    assert refresh.status_code == 401
