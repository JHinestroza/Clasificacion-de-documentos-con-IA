"""Read-only account smoke check over verified HTTPS, with explicit login/logout."""

import json
import ssl
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

from document_platform.config import BootstrapSettings


def probe() -> None:
    """Use the ignored bootstrap credential; never display credentials or session tokens."""
    settings = BootstrapSettings()
    origin = f"https://localhost:{settings.api_port}"
    if origin not in settings.auth_allowed_origins:
        raise ValueError("The local HTTPS origin must be allowed")
    context = ssl.create_default_context(cafile=str(settings.tls_ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    cookies = CookieJar()
    client = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(cookies))

    def request(path: str, data: dict[str, str] | None = None, csrf: str | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if csrf:
            headers.update({"Origin": origin, "X-CSRF-Token": csrf})
        body = json.dumps(data).encode() if data is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        with client.open(Request(origin + path, body, headers), timeout=10) as response:
            return json.load(response)

    ready = request("/api/v1/ready")
    if ready["status"] != "ready":
        raise RuntimeError("Dependencies are not ready")
    csrf = request("/api/v1/auth/csrf")["csrf_token"]
    signed = request(
        "/api/v1/auth/login",
        {
            "username": settings.bootstrap_admin_username,
            "password": settings.bootstrap_admin_password.get_secret_value(),
        },
        csrf,
    )
    try:
        assert request("/api/v1/auth/me")["is_superuser"] is True
        assert isinstance(request("/api/v1/users"), list)
        assert isinstance(request("/api/v1/permissions"), list)
        assert isinstance(request("/api/v1/audit"), list)
    finally:
        request("/api/v1/auth/logout", {}, signed["csrf_token"])
    try:
        request("/api/v1/auth/me")
    except HTTPError as exc:
        if exc.code != 401:
            raise
    else:
        raise RuntimeError("Logout verification failed")
    print("HTTPS verified: ready, login, identity, users, permissions, audit, logout, 401.")


if __name__ == "__main__":
    try:
        probe()
    except Exception:  # noqa: BLE001 - suppress credential-bearing transport details
        raise SystemExit(
            "HTTPS identity check failed; check API, TLS and bootstrap credentials."
        ) from None
