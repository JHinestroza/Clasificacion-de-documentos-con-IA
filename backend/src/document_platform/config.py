"""Validated configuration shared by the API and worker entry points."""

import logging
import re
import ssl
from collections.abc import Mapping
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Self

from dotenv.parser import parse_stream
from pydantic import (
    Field,
    FilePath,
    ModelWrapValidatorHandler,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    SettingsError,
)
from pydantic_settings.sources.utils import parse_env_vars


class LiteralDotEnvSettingsSource(DotEnvSettingsSource):
    """Read dotenv credentials literally, rejecting ambiguous application entries."""

    @staticmethod
    def _static_read_env_file(
        file_path: Path,
        *,
        encoding: str | None = None,
        case_sensitive: bool = False,
        ignore_empty: bool = False,
        parse_none_str: str | None = None,
    ) -> Mapping[str, str | None]:
        values: dict[str, str | None] = {}
        seen: set[str] = set()
        with file_path.open(encoding=encoding or "utf-8") as stream:
            for binding in parse_stream(stream):
                if binding.error:
                    raise SettingsError("Dotenv contains an invalid statement")
                if binding.key is None:
                    continue
                normalized = binding.key.casefold()
                if normalized.startswith("app_") and normalized in seen:
                    raise SettingsError("Dotenv contains a duplicate application setting")
                seen.add(normalized)
                values[binding.key] = binding.value
        return parse_env_vars(values, case_sensitive, ignore_empty, parse_none_str)


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
    db_password: SecretStr = Field(repr=False, exclude=True)

    broker_host: str = Field(default="rabbitmq", min_length=1)
    broker_port: int = Field(default=5671, ge=1, le=65535)
    broker_user: str = Field(default="document_app", min_length=1)
    broker_vhost: str = Field(default="document_platform", min_length=1)
    broker_password: SecretStr = Field(repr=False, exclude=True)
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
    web_dist_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[3] / "frontend" / "dist"
    )
    dependency_timeout_seconds: int = Field(default=3, ge=2, le=10)
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    auth_allowed_origins: tuple[str, ...] = ("https://localhost:8443", "https://127.0.0.1:8443")
    auth_idle_seconds: int = Field(default=1800, ge=60, le=86400)
    auth_absolute_seconds: int = Field(default=28800, ge=600, le=604800)
    auth_login_window_seconds: int = Field(default=900, ge=60, le=3600)
    auth_login_max_attempts: int = Field(default=5, ge=1, le=20)
    auth_hash_concurrency: int = Field(default=2, ge=1, le=4)

    @field_validator("auth_allowed_origins")
    @classmethod
    def validate_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        from urllib.parse import urlsplit

        if not origins:
            raise ValueError("At least one HTTPS origin is required")
        for origin in origins:
            value = urlsplit(origin)
            if (
                value.scheme != "https"
                or not value.hostname
                or value.username
                or value.password
                or value.path
                or value.query
                or value.fragment
            ):
                raise ValueError("Origins must be exact HTTPS origins without paths or credentials")
        return origins

    @model_validator(mode="after")
    def validate_auth_durations(self) -> Self:
        if self.auth_idle_seconds > self.auth_absolute_seconds:
            raise ValueError("Idle session duration cannot exceed absolute duration")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Preserve environment precedence while avoiding dotenv interpolation."""
        if not isinstance(dotenv_settings, DotEnvSettingsSource):
            raise SettingsError("Unsupported dotenv settings source")
        literal_dotenv = LiteralDotEnvSettingsSource(
            settings_cls,
            env_file=dotenv_settings.env_file,
            env_file_encoding=dotenv_settings.env_file_encoding,
            dotenv_filtering=dotenv_settings.dotenv_filtering,
            case_sensitive=dotenv_settings.case_sensitive,
            env_prefix=dotenv_settings.env_prefix,
            env_prefix_target=dotenv_settings.env_prefix_target,
            env_nested_delimiter=dotenv_settings.env_nested_delimiter,
            env_nested_max_split=dotenv_settings.env_nested_max_split,
            env_ignore_empty=dotenv_settings.env_ignore_empty,
            env_parse_none_str=dotenv_settings.env_parse_none_str,
            env_parse_enums=dotenv_settings.env_parse_enums,
            env_file_depth=dotenv_settings.env_file_depth,
        )
        return init_settings, env_settings, literal_dotenv

    @classmethod
    def _settings_log_debug(cls, states: dict[str, dict[str, Any]]) -> None:
        """Keep Pydantic source debugging from logging raw credential values."""
        logging.getLogger(__name__).debug("settings_sources_processed count=%s", len(states))

    @field_validator("db_password", "broker_password")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        """Require explicit nonblank single-line credentials without echoing them."""
        raw = value.get_secret_value()
        if len(raw) < 32 or not raw.strip() or any(character in raw for character in "\r\n\0"):
            raise ValueError(
                "Credentials must contain one nonblank value of at least 32 characters"
            )
        return value

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
    def validate_ca(self) -> Self:
        try:
            ssl.create_default_context(cafile=str(self.tls_ca_file))
        except (OSError, ssl.SSLError):
            raise ValueError("Configured TLS CA file is invalid") from None
        return self

    @model_validator(mode="wrap")
    @classmethod
    def redact_validation_inputs(cls, value: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        """Wrap field and model validation so serialized errors cannot expose input."""
        try:
            return handler(value)
        except ValidationError as exc:
            errors: list[InitErrorDetails] = []
            for error in exc.errors(include_input=False, include_url=False):
                detail: InitErrorDetails = {
                    "type": error["type"],
                    "loc": error["loc"],
                    "input": None,
                }
                if "ctx" in error:
                    detail["ctx"] = error["ctx"]
                errors.append(detail)
            raise ValidationError.from_exception_data(
                cls.__name__, errors, hide_input=True
            ) from None


class DatabaseAdminSettings(Settings):
    """Administrative credentials are loaded only by explicit provisioning/migration tools."""

    db_admin_user: str = "postgres"
    db_admin_password: SecretStr = Field(repr=False, exclude=True)

    @field_validator("db_admin_password")
    @classmethod
    def validate_admin_secret(cls, value: SecretStr) -> SecretStr:
        return cls.validate_secret(value)


class BootstrapSettings(Settings):
    """Explicit portal bootstrap credentials, distinct from PostgreSQL administration."""

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: SecretStr = Field(repr=False, exclude=True)

    @field_validator("bootstrap_admin_password")
    @classmethod
    def validate_bootstrap_secret(cls, value: SecretStr) -> SecretStr:
        if not 16 <= len(value.get_secret_value()) <= 128 or not value.get_secret_value().strip():
            raise ValueError("Bootstrap password must contain 16 to 128 nonblank characters")
        return value
