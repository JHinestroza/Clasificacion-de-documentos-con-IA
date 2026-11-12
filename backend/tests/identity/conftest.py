"""Isolated, additive PostgreSQL test databases; no production data or cleanup drops."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from document_platform.config import DatabaseAdminSettings
from document_platform.identity_admin import initialize_database
from document_platform.identity_runtime import build_identity_service

ROOT = Path(__file__).resolve().parents[3]
TEST_PASSWORD = "Synthetic-account-password-2026!"


def new_environment() -> tuple:
    settings = DatabaseAdminSettings(_env_file=ROOT / ".env")
    settings = settings.model_copy(
        update={
            "db_name": "document_platform_test_" + uuid4().hex[:16],
            "tls_ca_file": settings.tls_ca_file.resolve(),
        }
    )
    initialize_database(settings)
    service = build_identity_service(settings)
    admin = service.bootstrap_superuser("test_admin", TEST_PASSWORD)
    record = ROOT / ".local/identity-test-databases.json"
    names = json.loads(record.read_text(encoding="utf-8")) if record.exists() else []
    names.append(settings.db_name)
    record.write_text(json.dumps(names, indent=2), encoding="utf-8")
    return settings, service, admin


@pytest.fixture(scope="session")
def pg_environment() -> tuple:
    if os.environ.get("RUN_PG_INTEGRATION") != "1":
        pytest.skip("Set RUN_PG_INTEGRATION=1 for the real, synthetic PostgreSQL integration suite")
    return new_environment()


@pytest.fixture
def account(pg_environment: tuple) -> tuple:
    settings, service, admin = pg_environment
    login = service.login(admin.username, TEST_PASSWORD)
    user = service.create_user(
        login.token, login.csrf_token, "user_" + uuid4().hex[:16], TEST_PASSWORD
    )
    return settings, service, admin, login, user
