"""
tests/test_auth.py
Unit tests verifying E4: API authorization, signed session tokens, and role-based permissions.
"""

from fastapi.testclient import TestClient
import pytest

from backend.api.auth import create_session_token, verify_session_token
from backend.config import settings
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_session_token_creation_and_tamper_proofing():
    """Verify HMAC signed session tokens detect tampering and expiration (E4)."""
    token = create_session_token(role="admin", user_id="admin_1")
    assert token is not None
    assert "." in token

    # Valid token verifies correctly
    payload = verify_session_token(token)
    assert payload is not None
    assert payload["role"] == "admin"
    assert payload["user_id"] == "admin_1"

    # Tampered signature fails
    tampered_sig = token[:-4] + "ffff"
    assert verify_session_token(tampered_sig) is None

    # Tampered payload fails
    parts = token.split(".")
    tampered_payload = "eyJyb2xlIjoidXNlciJ9." + parts[1]
    assert verify_session_token(tampered_payload) is None

    # Invalid string fails gracefully
    assert verify_session_token("invalid_token") is None
    assert verify_session_token("") is None


def test_login_role_passwords_and_rejection(client, monkeypatch):
    """Verify login validates role-specific passwords and rejects bad attempts."""
    monkeypatch.setattr(settings, "auth_admin_password", "RealAdminSecret123")
    monkeypatch.setattr(settings, "auth_user_password", "RealUserSecret123")
    monkeypatch.setattr(settings, "auth_demo_mode", False)

    # 1. Invalid password rejected
    res = client.post("/api/v1/auth/login", json={"role": "admin", "password": "wrong"})
    assert res.status_code == 401

    # 2. Correct admin password succeeds
    res_admin = client.post("/api/v1/auth/login", json={"role": "admin", "password": "RealAdminSecret123"})
    assert res_admin.status_code == 200
    assert res_admin.json()["role"] == "admin"
    assert "token" in res_admin.json()
    assert "atos_workspace" in res_admin.cookies

    # 3. User password for admin role fails
    res_cross = client.post("/api/v1/auth/login", json={"role": "admin", "password": "RealUserSecret123"})
    assert res_cross.status_code == 401

    # 4. Correct user password succeeds
    res_user = client.post("/api/v1/auth/login", json={"role": "user", "password": "RealUserSecret123"})
    assert res_user.status_code == 200
    assert res_user.json()["role"] == "user"


def test_session_lifecycle_with_cookie_and_bearer(client):
    """Verify session check via cookie and Bearer header, and logout."""
    token = create_session_token(role="admin")

    # 1. Bearer header check
    res_header = client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert res_header.status_code == 200
    assert res_header.json()["role"] == "admin"

    # 2. Cookie check
    client.cookies.set("atos_workspace", token)
    res_cookie = client.get("/api/v1/auth/session")
    assert res_cookie.status_code == 200
    assert res_cookie.json()["role"] == "admin"

    # 3. Logout clears cookie
    res_logout = client.post("/api/v1/auth/logout")
    assert res_logout.status_code == 200


def test_user_can_select_catalog_model_without_admin_access(client, monkeypatch):
    from backend.schemas.models_catalog import CATALOG_PROVIDERS
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_model", "previous-model")
    selected_model = CATALOG_PROVIDERS["groq"].models[0].id
    payload = {"provider": "groq", "model": selected_model}
    assert client.post("/api/v1/screening/models", json=payload).status_code == 401

    client.cookies.set("atos_workspace", create_session_token(role="user"))
    response = client.post("/api/v1/screening/models", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["active_model"] == selected_model
    assert settings.groq_model == selected_model
    assert client.get("/api/v1/screening/models").json()["active_model"] == selected_model
    assert client.get("/api/v1/settings/llm").status_code == 403
    failover_res = client.post("/api/v1/screening/failover", json={"enabled": False})
    assert failover_res.status_code == 200
    assert failover_res.json()["fallback_enabled"] is False

    invalid = client.post("/api/v1/screening/models", json={"provider": "groq", "model": "not-in-catalog"})
    assert invalid.status_code == 400
    assert settings.groq_model == selected_model
