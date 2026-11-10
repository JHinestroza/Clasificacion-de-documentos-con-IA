"""Exercise bootstrap integrity using synthetic development certificates."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from dotenv import dotenv_values

from document_platform.config import Settings
from scripts.bootstrap_local import ASSET_PATHS, ENV_SECRETS, BootstrapError, bootstrap


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    output = tmp_path / "local-assets"
    bootstrap(output)
    return output


def snapshot(output: Path) -> dict[Path, str]:
    return {path: hashlib.sha256((output / path).read_bytes()).hexdigest() for path in ASSET_PATHS}


def environment(output: Path) -> dict[str, str | None]:
    return dict(dotenv_values(output.parent / ".env", interpolate=False))


def legacy_environment(output: Path) -> dict[str, str]:
    """Represent a synthetic F002 installation, keeping its original credential values."""
    values = environment(output)
    credentials = {name: str(values[name]) for name in ENV_SECRETS}
    directory = output / "secrets"
    directory.mkdir()
    for name, filename in ENV_SECRETS.items():
        (directory / filename).write_text(credentials[name] + "\n", encoding="utf-8")
    (output.parent / ".env").write_text(
        "# Preserve this header\n"
        "APP_CUSTOM='a # value'\n"
        f"APP_DB_PASSWORD_FILE='{output.name}/secrets/db_app_password' # database note\n"
        f"APP_BROKER_PASSWORD_FILE='{output.name}/secrets/broker_app_password'\n",
        encoding="utf-8",
    )
    return credentials


def test_rerun_preserves_certificates_credentials_and_hashes(assets: Path) -> None:
    before = snapshot(assets)
    dotenv = (assets.parent / ".env").read_bytes()
    assert bootstrap(assets) is False
    assert bootstrap(assets, check_only=True) is False
    assert snapshot(assets) == before
    assert (assets.parent / ".env").read_bytes() == dotenv
    assert not (assets / "secrets").exists()


def test_fresh_environment_has_credentials_and_usable_tls_paths(assets: Path) -> None:
    values = environment(assets)
    for name in ENV_SECRETS:
        assert values[name] is not None and len(str(values[name])) == 64
    assert len({values[name] for name in ENV_SECRETS}) == 3
    assert values["APP_TLS_CA_FILE"] == (assets / "certs/ca.crt").as_posix()
    assert values["APP_API_CERT_FILE"] == (assets / "certs/api.crt").as_posix()
    assert values["APP_API_KEY_FILE"] == (assets / "certs/api.key").as_posix()


def test_incomplete_set_is_not_repaired_or_rotated(assets: Path) -> None:
    previous_environment = (assets.parent / ".env").read_bytes()
    (assets / "certs/api.key").unlink()
    with pytest.raises(BootstrapError, match="incomplete"):
        bootstrap(assets)
    assert not (assets / "certs/api.key").exists()
    assert (assets.parent / ".env").read_bytes() == previous_environment


def test_check_only_never_creates_assets(tmp_path: Path) -> None:
    target = tmp_path / "absent"
    with pytest.raises(BootstrapError, match="do not exist"):
        bootstrap(target, check_only=True)
    assert not target.exists()


def test_mismatched_server_key_is_rejected_without_repair(assets: Path) -> None:
    replacement = (assets / "certs/postgres.key").read_bytes()
    (assets / "certs/api.key").write_bytes(replacement)
    with pytest.raises(BootstrapError, match="invalid"):
        bootstrap(assets)
    assert (assets / "certs/api.key").read_bytes() == replacement


def test_certificate_signed_by_another_ca_is_rejected(assets: Path, tmp_path: Path) -> None:
    other = tmp_path / "other-authority"
    bootstrap(other)
    for suffix in ("crt", "key"):
        relative = Path(f"certs/api.{suffix}")
        (assets / relative).write_bytes((other / relative).read_bytes())
    with pytest.raises(BootstrapError, match="invalid"):
        bootstrap(assets, check_only=True)


def test_cli_does_not_print_credentials_or_private_keys(tmp_path: Path) -> None:
    output = tmp_path / "cli-assets"
    script = Path(__file__).resolve().parents[1] / "scripts/bootstrap_local.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output-dir", str(output)],
        check=True,
        capture_output=True,
    )
    combined = result.stdout + result.stderr
    assert b"PRIVATE KEY" not in combined
    values = environment(output)
    for name in ENV_SECRETS:
        assert str(values[name]).encode() not in combined


def test_migration_preserves_values_comments_and_legacy_files(assets: Path) -> None:
    credentials = legacy_environment(assets)
    before = snapshot(assets)
    assert bootstrap(assets) is True
    assert snapshot(assets) == before
    values = environment(assets)
    assert all(values[name] == value for name, value in credentials.items())
    assert values["APP_CUSTOM"] == "a # value"
    content = (assets.parent / ".env").read_text(encoding="utf-8")
    assert "# Preserve this header" in content and "# database note" in content
    assert "APP_DB_PASSWORD_FILE" not in values and "APP_BROKER_PASSWORD_FILE" not in values
    for name, filename in ENV_SECRETS.items():
        assert (assets / "secrets" / filename).read_text().rstrip("\n") == credentials[name]
    assert bootstrap(assets) is False


def test_check_only_refuses_unmigrated_credentials_without_changes(assets: Path) -> None:
    legacy_environment(assets)
    before = (assets.parent / ".env").read_bytes()
    with pytest.raises(BootstrapError, match="migration"):
        bootstrap(assets, check_only=True)
    assert (assets.parent / ".env").read_bytes() == before


def test_migration_keeps_special_characters_literal(assets: Path) -> None:
    legacy_environment(assets)
    special = "special-'quote-\\-#-${NOT_EXPANDED}-" + "s" * 32
    (assets / "secrets/db_app_password").write_text(special + "\n", encoding="utf-8")
    bootstrap(assets)
    assert environment(assets)["APP_DB_PASSWORD"] == special


def test_partial_credentials_are_not_filled_or_rotated(assets: Path) -> None:
    content = "# user config\nAPP_DB_PASSWORD='" + "p" * 40 + "'\n"
    (assets.parent / ".env").write_text(content, encoding="utf-8")
    before = snapshot(assets)
    with pytest.raises(BootstrapError, match="missing or invalid"):
        bootstrap(assets)
    assert (assets.parent / ".env").read_text() == content
    assert snapshot(assets) == before


def test_empty_template_placeholders_can_be_prepared(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{name}=" for name in ENV_SECRETS), encoding="utf-8")
    output = tmp_path / "assets"
    assert bootstrap(output) is True
    assert all(len(str(environment(output)[name])) == 64 for name in ENV_SECRETS)
    settings = Settings(_env_file=path)
    assert settings.tls_ca_file == output / "certs/ca.crt"
    assert settings.api_cert_file == output / "certs/api.crt"
    assert settings.api_key_file == output / "certs/api.key"


def test_missing_tls_settings_are_reported_without_mutation(assets: Path) -> None:
    path = assets.parent / ".env"
    content = "\n".join(
        line for line in path.read_text().splitlines() if not line.startswith("APP_TLS_CA_FILE=")
    )
    path.write_text(content, encoding="utf-8")
    before = snapshot(assets)
    with pytest.raises(BootstrapError, match="TLS paths require"):
        bootstrap(assets, check_only=True)
    assert path.read_text() == content
    assert snapshot(assets) == before
    assert bootstrap(assets) is True
    assert Settings(_env_file=path).tls_ca_file == assets / "certs/ca.crt"


def test_custom_tls_setting_is_preserved_when_filling_missing_paths(assets: Path) -> None:
    path = assets.parent / ".env"
    value = (assets / "certs/api.crt").as_posix()
    credentials = environment(assets)
    path.write_text(
        "# Custom TLS configuration\n"
        f"APP_API_CERT_FILE='{value}' # retain this note\n"
        + "\n".join(f"{name}='{credentials[name]}'" for name in ENV_SECRETS),
        encoding="utf-8",
    )
    assert bootstrap(assets) is True
    assert "# retain this note" in path.read_text()
    assert environment(assets)["APP_API_CERT_FILE"] == value
    assert Settings(_env_file=path).api_cert_file == assets / "certs/api.crt"


@pytest.mark.parametrize(
    "filename", [".env.example", ".ENV.EXAMPLE", "secrets.env", ".ENV", ".env.example."]
)
def test_unsafe_environment_destinations_are_rejected_before_creation(
    tmp_path: Path, filename: str
) -> None:
    path = tmp_path / filename
    path.write_text("# retain original content\n", encoding="utf-8")
    output = tmp_path / "absent-assets"
    with pytest.raises(BootstrapError, match="private .env file"):
        bootstrap(output, env_file=path)
    assert path.read_text() == "# retain original content\n"
    assert not output.exists()


def test_explicit_private_environment_destination_is_supported(tmp_path: Path) -> None:
    output = tmp_path / "assets"
    path = tmp_path / ".env.development"
    assert bootstrap(output, env_file=path) is True
    assert Settings(_env_file=path).tls_ca_file == output / "certs/ca.crt"
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("check_only", [False, True])
def test_empty_configured_tls_path_is_rejected_without_mutation(
    assets: Path, check_only: bool
) -> None:
    path = assets.parent / ".env"
    content = "\n".join(
        "APP_TLS_CA_FILE=''" if line.startswith("APP_TLS_CA_FILE=") else line
        for line in path.read_text().splitlines()
    )
    path.write_text(content, encoding="utf-8")
    before = snapshot(assets)
    with pytest.raises(BootstrapError, match="TLS paths must not be empty"):
        bootstrap(assets, check_only=check_only)
    assert path.read_text() == content
    assert snapshot(assets) == before


def test_conflicting_legacy_credentials_are_rejected_without_changes(assets: Path) -> None:
    credentials = legacy_environment(assets)
    content = "\n".join(f"{name}='{value}'" for name, value in credentials.items())
    content = content.replace(credentials["APP_DB_PASSWORD"], "different-" + "x" * 40)
    (assets.parent / ".env").write_text(content, encoding="utf-8")
    before = snapshot(assets)
    with pytest.raises(BootstrapError, match="conflict"):
        bootstrap(assets)
    assert (assets.parent / ".env").read_text() == content
    assert snapshot(assets) == before


def test_duplicate_credentials_are_rejected_case_insensitively(assets: Path) -> None:
    path = assets.parent / ".env"
    content = path.read_text() + "app_db_password='" + "d" * 40 + "'\n"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(BootstrapError, match="duplicate"):
        bootstrap(assets)
    assert path.read_text() == content


def test_custom_legacy_path_is_not_silently_ignored(assets: Path) -> None:
    legacy_environment(assets)
    path = assets.parent / ".env"
    content = path.read_text().replace("secrets/db_app_password", "secrets/other_password")
    path.write_text(content, encoding="utf-8")
    with pytest.raises(BootstrapError, match="paths differ"):
        bootstrap(assets)
    assert path.read_text() == content


def test_failed_migration_does_not_echo_credentials(assets: Path, tmp_path: Path) -> None:
    content = "APP_DB_PASSWORD='" + "sensitive-" + "z" * 40 + "'\n"
    (assets.parent / ".env").write_text(content, encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts/bootstrap_local.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output-dir", str(assets)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert b"sensitive-" not in result.stdout + result.stderr


def test_concurrent_environment_edit_is_not_overwritten(
    assets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.bootstrap_local as module

    legacy_environment(assets)
    original = module._write_environment
    path = assets.parent / ".env"
    edited = path.read_bytes() + b"# concurrent user edit\n"

    def edit_before_publish(target: Path, content: bytes, expected: bytes | None) -> None:
        path.write_bytes(edited)
        original(target, content, expected)

    monkeypatch.setattr(module, "_write_environment", edit_before_publish)
    with pytest.raises(BootstrapError, match="changed during preparation"):
        bootstrap(assets)
    assert path.read_bytes() == edited


def test_expired_certificate_requires_explicit_renewal(assets: Path) -> None:
    ca = x509.load_pem_x509_certificate((assets / "certs/ca.crt").read_bytes())
    ca_key = serialization.load_pem_private_key((assets / "certs/ca.key").read_bytes(), None)
    assert isinstance(ca_key, ec.EllipticCurvePrivateKey)
    original = x509.load_pem_x509_certificate((assets / "certs/api.crt").read_bytes())
    expired = (
        x509.CertificateBuilder()
        .subject_name(original.subject)
        .issuer_name(ca.subject)
        .public_key(original.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=2))
        .not_valid_after(datetime.now(UTC) - timedelta(days=1))
    )
    for extension in original.extensions:
        expired = expired.add_extension(extension.value, extension.critical)
    replacement = expired.sign(ca_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
    (assets / "certs/api.crt").write_bytes(replacement)
    with pytest.raises(BootstrapError, match="invalid"):
        bootstrap(assets)
    assert (assets / "certs/api.crt").read_bytes() == replacement
