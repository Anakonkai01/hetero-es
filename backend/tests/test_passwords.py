"""Password rules for registration and password change: short enough to type, still not guessable in one try."""

import pytest

from backend.passwords import MIN_LENGTH, password_problem
from labkit import login


def register(client, **fields):
    body = {"username": "newcomer", "displayName": "New Comer", "password": "purple-train", **fields}
    return client.post("/api/v1/auth/register", json=body)


def test_the_minimum_is_eight_characters():
    assert MIN_LENGTH == 8
    assert password_problem("x7!kq2mz") is None
    assert "at least 8" in password_problem("x7!kq2m")
    assert "at least 8" in password_problem("")


@pytest.mark.parametrize(
    "weak",
    [
        "password",
        " password ",
        "        ",
        "Password123",
        "12345678",
        "QWERTYUIOP",
        "iloveyou",
        "aaaaaaaa",
        "00000000",
        "HeteroES1",
    ],
)
def test_obviously_guessable_passwords_are_refused(weak):
    assert "too easy" in password_problem(weak)


def test_the_password_may_not_be_the_account_name():
    assert "username or display name" in password_problem("Longusername", "longusername", "Someone")
    assert "username or display name" in password_problem("Some Person", "x", "some person")
    assert password_problem("Longusername-2", "longusername", "Someone") is None


def test_registration_accepts_a_short_but_unusual_password(setup):
    client, _, _ = setup
    assert register(client, password="x7!kq2mz").status_code == 201
    assert client.post("/api/v1/auth/login", json={"username": "newcomer", "password": "x7!kq2mz"}).status_code == 200


def test_registration_explains_why_a_password_was_refused(setup):
    client, _, _ = setup
    for password, words in (
        ("short7!", "at least 8"),
        ("password123", "too easy"),
        ("newcomer", "username or display name"),
    ):
        reply = register(client, password=password)
        assert reply.status_code == 422, password
        assert isinstance(reply.json()["message"], str) and words in reply.json()["message"], reply.text
    assert register(client, password="p" * 201).status_code == 422
    assert (
        client.post("/api/v1/auth/login", json={"username": "newcomer", "password": "password123"}).status_code == 401
    )


def test_password_change_follows_the_same_rules(setup):
    client, _, _ = setup
    session = login(client, "participant")
    change = lambda new: client.post(
        "/api/v1/auth/password", json={"currentPassword": "test-user-pass", "newPassword": new}, headers=session
    )
    assert "at least 8" in change("abc123!").json()["message"]
    assert "too easy" in change("password123").json()["message"]
    assert "username or display name" in change("participant").json()["message"]
    assert change("x7!kq2mz").status_code == 204
