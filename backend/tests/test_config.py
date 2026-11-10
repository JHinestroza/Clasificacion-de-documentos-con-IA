"""Configuration fails closed and does not expose secret file contents."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from document_platform.config import Settings
from document_platform.infrastructure.tls import api_ssl_context


def test_required_files_have_no_credential_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DB_PASSWORD_FILE", "BROKER_PASSWORD_FILE", "TLS_CA_FILE"):
        monkeypatch.delenv(f"APP_{name}", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_values_are_redacted(settings: Settings) -> None:
    secret = settings.db_password.get_secret_value()
    assert secret not in repr(settings)
    assert secret not in settings.model_dump_json()
    assert secret not in repr(settings.db_password)


def test_empty_secret_is_rejected_without_echoing_contents(
    settings_values: dict[str, Any],
) -> None:
    settings_values["db_password_file"].write_text("short-sensitive-value", encoding="utf-8")
    with pytest.raises(ValidationError) as caught:
        Settings(**settings_values)
    assert "short-sensitive-value" not in str(caught.value)


def test_invalid_ca_prevents_startup(settings_values: dict[str, Any]) -> None:
    settings_values["tls_ca_file"].write_text("not a certificate", encoding="utf-8")
    with pytest.raises(ValidationError, match="TLS CA file is invalid"):
        Settings(**settings_values)


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


def test_dotenv_loads_paths_without_storing_secret_values(
    settings_values: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    names = ("db_password_file", "broker_password_file", "tls_ca_file")
    dotenv = "\n".join(f"APP_{name.upper()}={settings_values[name].as_posix()}" for name in names)
    (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    loaded = Settings()
    assert loaded.db_password == Settings(**settings_values).db_password
    assert loaded.api_host == "127.0.0.1"
