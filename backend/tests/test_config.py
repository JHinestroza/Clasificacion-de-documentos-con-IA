"""Dotenv credentials are required, validated and never disclosed in diagnostics."""

import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsError

from document_platform.config import Settings
from document_platform.infrastructure.tls import api_ssl_context


def test_required_values_have_no_credential_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DB_PASSWORD", "BROKER_PASSWORD", "TLS_CA_FILE"):
        monkeypatch.delenv(f"APP_{name}", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_values_are_redacted(settings: Settings) -> None:
    for field in ("db_password", "broker_password"):
        secret = getattr(settings, field).get_secret_value()
        assert secret not in repr(settings)
        assert secret not in settings.model_dump_json()
        assert secret not in repr(settings.model_dump())
        assert field not in settings.model_dump()
        assert secret not in repr(getattr(settings, field))


def test_source_debugging_does_not_log_credentials(
    settings_values: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("PYDANTIC_SETTINGS_DEBUG", "true")
    with caplog.at_level(logging.DEBUG):
        Settings(**settings_values)
    assert "settings_sources_processed" in caplog.text
    for field in ("db_password", "broker_password"):
        assert settings_values[field] not in caplog.text


@pytest.mark.parametrize("field", ["db_password", "broker_password"])
@pytest.mark.parametrize(
    "value", ["", "short-sensitive-value", " " * 40, "x" * 32 + "\n", "x" * 32 + "\0"]
)
def test_invalid_secret_is_rejected_without_echoing_contents(
    settings_values: dict[str, Any], field: str, value: str
) -> None:
    settings_values[field] = value
    with pytest.raises(ValidationError) as caught:
        Settings(**settings_values)
    if value:
        diagnostic = str(caught.value) + repr(caught.value) + caught.value.json()
        assert value not in diagnostic
    assert all(error.get("input") is None for error in caught.value.errors())


def test_invalid_ca_prevents_startup(settings_values: dict[str, Any]) -> None:
    settings_values["tls_ca_file"].write_text("not a certificate", encoding="utf-8")
    with pytest.raises(ValidationError, match="TLS CA file is invalid") as caught:
        Settings(**settings_values)
    for field in ("db_password", "broker_password"):
        assert settings_values[field] not in caught.value.json() + repr(caught.value.errors())


@pytest.mark.parametrize("host", ["amqps://rabbitmq", "user@rabbitmq", "rabbitmq/path", "bad host"])
def test_hosts_cannot_change_the_connection_target(
    settings_values: dict[str, Any], host: str
) -> None:
    with pytest.raises(ValidationError, match="Host must be a DNS name or an IP address"):
        Settings(**(settings_values | {"broker_host": host}))


def test_api_requires_its_own_certificate_and_key(settings_values: dict[str, Any]) -> None:
    settings_values.pop("api_cert_file")
    settings_values.pop("api_key_file")
    common_settings = Settings(**settings_values)
    with pytest.raises(ValueError, match="API certificate"):
        api_ssl_context(common_settings)


def test_invalid_api_key_is_rejected(settings: Settings) -> None:
    assert settings.api_key_file is not None
    settings.api_key_file.write_text("not a private key", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid or do not match"):
        api_ssl_context(settings)


def test_dotenv_loads_required_credentials(
    settings_values: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    dotenv = "\n".join(
        (
            f"APP_DB_PASSWORD={settings_values['db_password']}",
            f"APP_BROKER_PASSWORD={settings_values['broker_password']}",
            f"APP_TLS_CA_FILE={settings_values['tls_ca_file'].as_posix()}",
        )
    )
    (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    loaded = Settings()
    assert loaded.db_password == Settings(**settings_values).db_password
    assert loaded.broker_password == Settings(**settings_values).broker_password
    assert loaded.api_host == "127.0.0.1"


def test_environment_overrides_dotenv_credentials(
    settings_values: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"APP_DB_PASSWORD={settings_values['db_password']}\n"
        f"APP_BROKER_PASSWORD={settings_values['broker_password']}\n"
        f"APP_TLS_CA_FILE={settings_values['tls_ca_file'].as_posix()}\n",
        encoding="utf-8",
    )
    override = "synthetic-environment-override-" + "e" * 32
    monkeypatch.setenv("APP_DB_PASSWORD", override)
    assert Settings().db_password.get_secret_value() == override


def test_dotenv_credentials_preserve_literal_variable_syntax(
    settings_values: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPLACEMENT", "must-not-be-substituted")
    literal = "synthetic-${REPLACEMENT}-" + "s" * 32
    (tmp_path / ".env").write_text(
        f"APP_DB_PASSWORD='{literal}'\n"
        f"APP_BROKER_PASSWORD={settings_values['broker_password']}\n"
        f"APP_TLS_CA_FILE={settings_values['tls_ca_file'].as_posix()}\n",
        encoding="utf-8",
    )
    assert Settings().db_password.get_secret_value() == literal


@pytest.mark.parametrize(
    "statement",
    [
        "app_db_password='ambiguous-synthetic-value'",
        "APP_DB_PASSWORD='unterminated-synthetic-value",
    ],
)
def test_ambiguous_or_malformed_dotenv_is_rejected_without_values(
    settings_values: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, statement: str
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"APP_DB_PASSWORD={settings_values['db_password']}\n{statement}\n",
        encoding="utf-8",
    )
    with pytest.raises(SettingsError) as caught:
        Settings()
    assert "synthetic-value" not in str(caught.value)


def test_legacy_secret_file_settings_do_not_supply_credentials(
    settings_values: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("DB_PASSWORD", "BROKER_PASSWORD"):
        monkeypatch.delenv(f"APP_{name}", raising=False)
    legacy = tmp_path / "old-password"
    legacy.write_text("synthetic-legacy-secret-" + "l" * 32, encoding="utf-8")
    (tmp_path / ".env").write_text(
        f"APP_DB_PASSWORD_FILE={legacy.as_posix()}\n"
        f"APP_BROKER_PASSWORD_FILE={legacy.as_posix()}\n"
        f"APP_TLS_CA_FILE={settings_values['tls_ca_file'].as_posix()}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as caught:
        Settings()
    assert {error["loc"] for error in caught.value.errors()} == {
        ("db_password",),
        ("broker_password",),
    }
