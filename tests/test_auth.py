"""Testy modulu autoryzacji."""
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_user


@pytest.fixture(autouse=True)
def mock_email():
    """Nie wysylaj prawdziwych e-maili podczas testow."""
    with patch("app.services.auth_service.send_activation_email", new_callable=AsyncMock), \
         patch("app.services.auth_service.send_password_reset_email", new_callable=AsyncMock):
        yield


class TestRegister:
    def test_register_success(self, client, db):
        resp = client.post("/api/v1/auth/register", json={
            "email": "newuser@test.pl",
            "password": "haslo1234",
            "first_name": "Anna",
            "last_name": "Nowak",
        })
        assert resp.status_code == 201
        assert "aktywowac" in resp.json()["message"].lower()

    def test_register_duplicate_email(self, client, db):
        make_user(db, "dup@test.pl")
        resp = client.post("/api/v1/auth/register", json={
            "email": "dup@test.pl",
            "password": "haslo1234",
            "first_name": "X",
            "last_name": "Y",
        })
        assert resp.status_code == 409

    def test_register_weak_password(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "weak@test.pl",
            "password": "123",
            "first_name": "X",
            "last_name": "Y",
        })
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client, db):
        make_user(db, "login_ok@test.pl", password="haslo1234")
        resp = client.post("/api/v1/auth/login", json={
            "email": "login_ok@test.pl",
            "password": "haslo1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, db):
        make_user(db, "login_bad@test.pl", password="haslo1234")
        resp = client.post("/api/v1/auth/login", json={
            "email": "login_bad@test.pl",
            "password": "zlehaslo",
        })
        assert resp.status_code == 401

    def test_login_inactive_account(self, client, db):
        make_user(db, "inactive@test.pl", active=False)
        resp = client.post("/api/v1/auth/login", json={
            "email": "inactive@test.pl",
            "password": "haslo1234",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@test.pl",
            "password": "haslo1234",
        })
        assert resp.status_code == 401


class TestActivation:
    def test_activate_valid_token(self, client, db):
        from datetime import datetime, timedelta, timezone
        from app.models.user import User
        from app.utils.security import hash_password

        user = User(
            email="toactivate@test.pl",
            hashed_password=hash_password("haslo1234"),
            first_name="T",
            last_name="T",
            is_active=False,
            activation_token="valid-token-abc",
            activation_token_expires=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(user)
        db.commit()

        resp = client.get("/api/v1/auth/activate?token=valid-token-abc")
        assert resp.status_code == 200
        db.refresh(user)
        assert user.is_active is True
        assert user.activation_token is None

    def test_activate_invalid_token(self, client):
        resp = client.get("/api/v1/auth/activate?token=nie-istnieje")
        assert resp.status_code == 400


class TestRefreshToken:
    def test_refresh_success(self, client, db):
        user = make_user(db, "refresh@test.pl")
        from app.utils.security import create_refresh_token
        refresh = create_refresh_token(user.id)

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_refresh_invalid_token(self, client):
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "fake"})
        assert resp.status_code == 401


class TestProtectedEndpoint:
    def test_no_token_returns_401(self, client):
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 403  # HTTPBearer zwraca 403 gdy brak nagłówka

    def test_valid_token_returns_200(self, client, db):
        user = make_user(db, "protected@test.pl")
        from tests.conftest import auth_headers
        resp = client.get("/api/v1/users/me", headers=auth_headers(user))
        assert resp.status_code == 200
        assert resp.json()["email"] == "protected@test.pl"
