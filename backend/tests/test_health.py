"""API health checks are narrow and redact dependency failures."""

import logging

import pytest
from fastapi.testclient import TestClient

from document_platform.application.readiness import ReadinessService
from document_platform.config import Settings
from document_platform.main import create_app


def available() -> None:
    return None


def test_health_does_not_probe_dependencies(settings: Settings) -> None:
    def must_not_run() -> None:
        raise AssertionError("Health must not connect to dependencies")

    client = TestClient(
        create_app(settings, ReadinessService(must_not_run, must_not_run)),
        base_url="https://testserver",
    )
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 404


def test_ready_reports_success(settings: Settings) -> None:
    client = TestClient(
        create_app(settings, ReadinessService(available, available)),
        base_url="https://testserver",
    )
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "broker": "ok"}}


def test_ready_redacts_dependency_errors(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    secret = settings.db_password.get_secret_value()

    def unavailable() -> None:
        raise ConnectionError(f"postgresql://user:{secret}@private-host/internal-database")

    client = TestClient(
        create_app(settings, ReadinessService(unavailable, available)),
        base_url="https://testserver",
    )
    with caplog.at_level(logging.WARNING):
        response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable", "broker": "ok"},
    }
    assert secret not in response.text + caplog.text
    assert "private-host" not in response.text + caplog.text


def test_http_and_spoofed_forwarded_proto_are_rejected(settings: Settings) -> None:
    client = TestClient(create_app(settings, ReadinessService(available, available)))
    response = client.get("/api/v1/health", headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 400
    assert response.json() == {"detail": "HTTPS required"}
