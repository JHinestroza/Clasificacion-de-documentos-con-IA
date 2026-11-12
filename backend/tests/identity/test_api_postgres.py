"""HTTP identity contracts with real PostgreSQL state and synthetic users."""

import pytest
from fastapi.testclient import TestClient

from document_platform.config import Settings
from document_platform.main import create_app

from .conftest import TEST_PASSWORD

ORIGIN = "https://localhost:8443"


@pytest.fixture
def api(account: tuple):
    settings, service, admin, login, user = account
    runtime = Settings(
        _env_file=None,
        **settings.model_dump(),
        db_password=settings.db_password,
        broker_password=settings.broker_password,
    )
    with TestClient(create_app(runtime, identity=service), base_url=ORIGIN) as client:
        yield client, service, admin, user


def sign_in(client: TestClient, username: str, password: str = TEST_PASSWORD):
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    return response


def headers(client: TestClient) -> dict:
    return {"Origin": ORIGIN, "X-CSRF-Token": client.cookies.get("__Host-csrf")}


def test_login_secure_cookies_no_raw_session_json_and_logout(api) -> None:
    client, service, admin, user = api
    response = sign_in(client, user.username)
    assert response.status_code == 200
    cookie = ";".join(response.headers.get_list("set-cookie")).lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "domain=" not in cookie and "path=/" in cookie
    token = client.cookies.get("__Host-session")
    assert token not in response.text and TEST_PASSWORD not in response.text
    assert client.get("/api/v1/auth/me").json()["id"] == str(user.id)
    assert client.get("/api/v1/auth/me").headers["cache-control"] == "no-store"
    assert client.post("/api/v1/auth/logout", headers=headers(client)).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("origin", [None, "http://localhost:8443", "https://evil.invalid"])
def test_login_requires_csrf_and_exact_https_origin(api, origin) -> None:
    client, service, admin, user = api
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    request_headers = {"X-CSRF-Token": csrf}
    if origin:
        request_headers["Origin"] = origin
    response = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": TEST_PASSWORD},
        headers=request_headers,
    )
    assert response.status_code == 403
    assert "__Host-session" not in client.cookies


def test_missing_csrf_cookie_or_header_is_rejected(api) -> None:
    client, service, admin, user = api
    client.get("/api/v1/auth/csrf")
    response = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": TEST_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 403


def test_non_admin_cannot_manage_accounts_and_denial_is_audited(api) -> None:
    client, service, admin, user = api
    assert sign_in(client, user.username).status_code == 200
    assert client.get("/api/v1/users").status_code == 403
    assert client.get("/api/v1/audit").status_code == 403
    response = client.post(
        "/api/v1/users",
        json={"username": "not_created", "password": TEST_PASSWORD, "is_superuser": True},
        headers=headers(client),
    )
    assert response.status_code == 403
    admin_login = service.login(admin.username, TEST_PASSWORD)
    audit = service.list_audit(admin_login.token, 100)
    assert any(
        entry.actor_id == user.id and entry.action == "users.create" and entry.outcome == "denied"
        for entry in audit
    )
    assert not any(item.username == "not_created" for item in service.list_users(admin_login.token))


def test_admin_can_create_assign_read_audit_and_revoke_sessions(api) -> None:
    client, service, admin, user = api
    assert sign_in(client, admin.username).status_code == 200
    response = client.put(
        f"/api/v1/users/{user.id}/permissions",
        json={"permissions": ["audit.read"], "reason": "Synthetic API grant"},
        headers=headers(client),
    )
    assert response.status_code == 200 and response.json()["permissions"] == ["audit.read"]
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    assert "password_hash" not in response.text and TEST_PASSWORD not in response.text
    response = client.get("/api/v1/audit")
    assert response.status_code == 200 and "subject_hash" not in response.text
    client.post("/api/v1/auth/logout", headers=headers(client))
    assert sign_in(client, user.username).status_code == 200
    assert client.get("/api/v1/audit").status_code == 200
    assert client.get("/api/v1/users").status_code == 403


def test_invalid_bodies_and_pagination_do_not_echo_credentials(api, caplog) -> None:
    client, service, admin, user = api
    private = "sensitive-synthetic-marker-that-must-not-be-rendered"
    response = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": private, "unexpected": private},
    )
    assert response.status_code == 422
    assert private not in response.text + caplog.text
    assert sign_in(client, admin.username).status_code == 200
    assert client.get("/api/v1/users?limit=1000").status_code == 422
    assert client.get("/api/v1/audit?offset=-1").status_code == 422


def test_password_change_clears_client_and_revokes_server_sessions(api) -> None:
    client, service, admin, user = api
    assert sign_in(client, user.username).status_code == 200
    old = client.cookies.get("__Host-session")
    response = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": TEST_PASSWORD,
            "new_password": "replacement-synthetic-password-2026!",
        },
        headers=headers(client),
    )
    assert response.status_code == 200
    assert "__Host-session" not in client.cookies
    from document_platform.domain.identity.models import AuthenticationError

    with pytest.raises(AuthenticationError):
        service.me(old)
    assert sign_in(client, user.username, "replacement-synthetic-password-2026!").status_code == 200


def test_storage_failure_is_generic_and_does_not_expose_traceback(api, monkeypatch) -> None:
    client, service, admin, user = api
    assert sign_in(client, user.username).status_code == 200

    def failure():
        raise RuntimeError("synthetic-private-database-error")

    monkeypatch.setattr(service, "_uow", failure)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 503
    assert "synthetic-private" not in response.text and "traceback" not in response.text.lower()


def test_http_cannot_reach_identity_even_with_forwarded_proto(api) -> None:
    client, service, admin, user = api
    response = client.get(
        "http://localhost:8443/api/v1/auth/csrf", headers={"X-Forwarded-Proto": "https"}
    )
    assert response.status_code == 400 and response.json()["detail"] == "HTTPS required"
