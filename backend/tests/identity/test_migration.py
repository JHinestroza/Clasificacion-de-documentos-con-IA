"""Offline migration output is credential-free and downgrade refuses destructive SQL."""

from io import StringIO

import pytest
from alembic import command

from document_platform.identity_admin import migration_config


def test_offline_sql_requires_no_credentials_or_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    import os

    monkeypatch.chdir(tmp_path)
    for name in tuple(os.environ):
        if name.startswith("APP_"):
            monkeypatch.delenv(name)
    output = StringIO()
    configuration = migration_config()
    configuration.output_buffer = output
    command.upgrade(configuration, "head", sql=True)
    sql = output.getvalue()
    for table in ("users", "permissions", "user_permissions", "sessions", "audit_logs"):
        assert "CREATE TABLE identity." + table in sql
    assert "DROP TABLE" not in sql
    assert "CREATE ROLE" not in sql and "APP_DB_PASSWORD" not in sql


def test_destructive_downgrade_is_not_available() -> None:
    configuration = migration_config()
    configuration.output_buffer = StringIO()
    with pytest.raises(RuntimeError, match="separately approved"):
        command.downgrade(configuration, "0001_identity:base", sql=True)
