"""Sessions survive reloads while expiry, signature checks and role gates remain enforced."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from backend.api.auth import create_session_token, verify_session_token
from backend.config import Settings, settings
from backend.main import app
from backend.services.session_secret import load_or_create_session_secret


def test_signing_key_survives_independent_settings_instances(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    path = tmp_path / "secret"
    first = Settings(_env_file=None, auth_secret_file=str(path))
    second = Settings(_env_file=None, auth_secret_file=str(path))
    assert first.auth_secret_key == second.auth_secret_key
    assert len(first.auth_secret_key) >= 32


def test_concurrent_workers_publish_one_complete_key(tmp_path):
    path = tmp_path / "secret"
    with ThreadPoolExecutor(max_workers=8) as pool:
        secrets = list(pool.map(lambda _: load_or_create_session_secret(str(path)), range(24)))
    assert len(set(secrets)) == 1
    assert len(secrets[0]) >= 32
    assert not list(tmp_path.glob(".auth-secret-*"))


def test_explicit_key_does_not_touch_secret_file(tmp_path):
    path = tmp_path / "unused"
    configured = Settings(_env_file=None, auth_secret_file=str(path), auth_secret_key="configured-key-" * 4)
    assert configured.auth_secret_key == "configured-key-" * 4
    assert not path.exists()


def test_invalid_stored_key_is_not_silently_rotated(tmp_path):
    path = tmp_path / "secret"
    path.write_text("invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="Stored session signing key is invalid"):
        load_or_create_session_secret(str(path))
    assert path.read_text() == "invalid"


def test_authenticated_cookie_survives_simulated_reload(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    path = str(tmp_path / "secret")
    first = Settings(_env_file=None, auth_secret_file=path)
    monkeypatch.setattr(settings, "auth_secret_key", first.auth_secret_key)
    monkeypatch.setattr(settings, "auth_required", True)
    token = create_session_token("user")
    monkeypatch.setattr(settings, "auth_secret_key", Settings(_env_file=None, auth_secret_file=path).auth_secret_key)
    client = TestClient(app)
    client.cookies.set("atos_workspace", token)
    assert client.get("/api/v1/auth/session").json()["role"] == "user"
    assert client.get("/api/v1/screening/models").status_code == 200
    assert client.get("/api/v1/settings/llm").status_code == 403
    client.cookies.clear()
    assert client.get("/api/v1/screening/models").status_code == 401


def test_persisted_secret_does_not_extend_expired_tokens(monkeypatch):
    monkeypatch.setattr("backend.api.auth.time.time", lambda: 1000)
    token = create_session_token("user")
    monkeypatch.setattr("backend.api.auth.time.time", lambda: 1000 + 43201)
    assert verify_session_token(token) is None
