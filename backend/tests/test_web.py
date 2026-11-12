"""The public bundle cannot expose source, credentials or paths outside compiled assets."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from document_platform.config import Settings
from document_platform.main import create_app


@pytest.fixture
def web_client(settings: Settings, tmp_path: Path) -> TestClient:
    root = tmp_path / "web"
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text(
        '<!doctype html><html lang="es"><div id="root"></div></html>', encoding="utf-8"
    )
    (assets / "index-1234abcd.js").write_text(
        'document.body.dataset.loaded="yes";', encoding="utf-8"
    )
    (assets / ".env").write_text("SYNTHETIC-PRIVATE-CONTENT", encoding="utf-8")
    (assets / "bundle.js.map").write_text("synthetic source map", encoding="utf-8")
    (tmp_path / ".env").write_text("SYNTHETIC-PRIVATE-CONTENT", encoding="utf-8")
    configuration = settings.model_copy(update={"web_dist_dir": root})
    return TestClient(create_app(configuration), base_url="https://localhost:8443")


def test_shell_and_assets_have_strict_headers(web_client: TestClient) -> None:
    response = web_client.get("/")
    assert response.status_code == 200 and '<div id="root">' in response.text
    assert response.headers["cache-control"] == "no-store"
    policy = response.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    response = web_client.get("/assets/index-1234abcd.js")
    assert response.status_code == 200 and "immutable" in response.headers["cache-control"]
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize(
    "path",
    [
        "/.env",
        "/src/main.tsx",
        "/package.json",
        "/assets/.env",
        "/assets/bundle.js.map",
        "/assets/%2e%2e/%2e%2e/.env",
        "/assets/index-1234abcd.js/../.env",
        "/assets/random.js",
    ],
)
def test_private_or_unversioned_files_are_not_served(web_client: TestClient, path: str) -> None:
    response = web_client.get(path)
    assert response.status_code == 404
    assert "SYNTHETIC-PRIVATE" not in response.text


def test_no_http_shell_or_proxy_override(web_client: TestClient) -> None:
    response = web_client.get("http://localhost:8443/", headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 400 and response.json()["detail"] == "HTTPS required"
    assert "content-security-policy" in response.headers


def test_missing_build_does_not_break_api(settings: Settings, tmp_path: Path) -> None:
    configuration = settings.model_copy(update={"web_dist_dir": tmp_path / "missing"})
    client = TestClient(create_app(configuration), base_url="https://testserver")
    assert client.get("/").status_code == 503
    assert str(tmp_path) not in client.get("/").text
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/no-such-endpoint").status_code == 404
