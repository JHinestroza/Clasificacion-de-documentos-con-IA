"""Validated configuration shared by the API and worker entry points."""

import re
import ssl
from ipaddress import ip_address
from pathlib import Path
from typing import Self

from pydantic import Field, FilePath, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load deployment settings and secrets without embedding credentials in source."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    db_host: str = Field(default="postgres", min_length=1)
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(default="document_platform", min_length=1)
    db_user: str = Field(default="document_app", min_length=1)
    db_password_file: FilePath

    broker_host: str = Field(default="rabbitmq", min_length=1)
    broker_port: int = Field(default=5671, ge=1, le=65535)
    broker_user: str = Field(default="document_app", min_length=1)
    broker_vhost: str = Field(default="document_platform", min_length=1)
    broker_password_file: FilePath
    broker_task_queue: str = Field(
        default="document_platform.processing", pattern=r"^document_platform\.[a-z0-9_.-]+$"
    )
    broker_task_exchange: str = Field(
        default="document_platform.tasks", pattern=r"^document_platform\.[a-z0-9_.-]+$"
    )

    tls_ca_file: FilePath
    api_cert_file: FilePath | None = None
    api_key_file: FilePath | None = None
    api_host: str = Field(default="127.0.0.1", min_length=1)
    api_port: int = Field(default=8443, ge=1, le=65535)
    dependency_timeout_seconds: int = Field(default=3, ge=2, le=10)
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    _db_password: SecretStr = PrivateAttr()
    _broker_password: SecretStr = PrivateAttr()

    @field_validator("db_host", "broker_host", "api_host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        """Accept DNS names or IP addresses, never URLs or credential-like netlocs."""
        try:
            ip_address(value)
        except ValueError:
            labels = value.removesuffix(".").split(".")
            if len(value) > 253 or any(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) is None
                for label in labels
            ):
                raise ValueError("Host must be a DNS name or an IP address") from None
        return value

    @model_validator(mode="after")
    def load_secrets(self) -> Self:
        self._db_password = _read_secret(self.db_password_file)
        self._broker_password = _read_secret(self.broker_password_file)
        try:
            ssl.create_default_context(cafile=str(self.tls_ca_file))
        except (OSError, ssl.SSLError):
            raise ValueError("Configured TLS CA file is invalid") from None
        return self

    @property
    def db_password(self) -> SecretStr:
        """Return the database secret with a redacted representation."""
        return self._db_password

    @property
    def broker_password(self) -> SecretStr:
        """Return the broker secret with a redacted representation."""
        return self._broker_password


def _read_secret(path: Path) -> SecretStr:
    try:
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError):
        raise ValueError("Configured secret file cannot be read") from None
    if len(value) < 32 or any(character in value for character in "\r\n\0"):
        raise ValueError("Secret files must contain one value of at least 32 characters")
    return SecretStr(value)
