from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app import main as main_module
from app.api import auth as auth_module


def test_auth_signup_creates_tenant_and_returns_token(monkeypatch) -> None:
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    async def _fake_create_tenant(name: str, slug: str) -> dict:
        assert name == "Acme Inc"
        assert slug == "acme-inc"
        return {"id": tenant_id, "name": name, "slug": slug}

    async def _fake_create_auth_user(email: str, password: str, resolved_tenant_id: str) -> dict:
        assert email == "owner@acme.test"
        assert password == "StrongPass123!"
        assert resolved_tenant_id == tenant_id
        return {"id": user_id, "email": email}

    async def _fake_password_sign_in(email: str, password: str) -> dict:
        assert email == "owner@acme.test"
        assert password == "StrongPass123!"
        return {
            "access_token": "header.payload.sig",
            "token_type": "bearer",
            "expires_in": 3600,
            "refresh_token": "refresh-token",
            "user": {
                "id": user_id,
                "email": email,
                "app_metadata": {"organization_id": tenant_id},
            },
        }

    monkeypatch.setattr(auth_module, "_require_auth_settings", lambda: None)
    monkeypatch.setattr(auth_module, "_create_tenant", _fake_create_tenant)
    monkeypatch.setattr(auth_module, "_create_auth_user", _fake_create_auth_user)
    monkeypatch.setattr(auth_module, "_password_sign_in", _fake_password_sign_in)

    client = TestClient(main_module.create_app())
    response = client.post(
        "/auth/signup",
        json={
            "email": "owner@acme.test",
            "password": "StrongPass123!",
            "tenant_name": "Acme Inc",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["message"] == "Signup successful"
    assert body["access_token"] == "header.payload.sig"
    assert body["tenant_id"] == tenant_id
    assert body["user_id"] == user_id
    assert body["email"] == "owner@acme.test"


def test_auth_login_returns_existing_tenant_token(monkeypatch) -> None:
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    async def _fake_password_sign_in(email: str, password: str) -> dict:
        assert email == "owner@acme.test"
        assert password == "StrongPass123!"
        return {
            "access_token": "header.payload.sig",
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {
                "id": user_id,
                "email": email,
                "app_metadata": {"organization_id": tenant_id},
            },
        }

    monkeypatch.setattr(auth_module, "_require_auth_settings", lambda: None)
    monkeypatch.setattr(auth_module, "_password_sign_in", _fake_password_sign_in)

    client = TestClient(main_module.create_app())
    response = client.post(
        "/auth/login",
        json={"email": "owner@acme.test", "password": "StrongPass123!"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Login successful"
    assert body["access_token"] == "header.payload.sig"
    assert body["tenant_id"] == tenant_id
    assert body["user_id"] == user_id


def test_auth_login_rejects_invalid_credentials(monkeypatch) -> None:
    async def _fake_password_sign_in(_email: str, _password: str) -> dict:
        raise auth_module.SupabaseAuthError(401, "Invalid email or password.")

    monkeypatch.setattr(auth_module, "_require_auth_settings", lambda: None)
    monkeypatch.setattr(auth_module, "_password_sign_in", _fake_password_sign_in)

    client = TestClient(main_module.create_app())
    response = client.post(
        "/auth/login",
        json={"email": "owner@acme.test", "password": "wrongpass1"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["message"] == "Login failed"
    assert body["detail"] == "Invalid email or password."
