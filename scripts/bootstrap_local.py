"""Prepare development TLS files and credentials in a private dotenv file.

This creates a development CA without installing it in the operating system trust
store. Filesystem permissions do not establish encryption at rest or Windows ACLs.
Existing assets are verified, never overwritten or silently rotated.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import secrets
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from dotenv.parser import Binding, parse_stream

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / ".local"
SERVICES = {
    "api": ("api", "localhost", "127.0.0.1"),
    "postgres": ("postgres",),
    "rabbitmq": ("rabbitmq",),
}
ENV_SECRETS = {
    "APP_DB_ADMIN_PASSWORD": "db_admin_password",
    "APP_DB_PASSWORD": "db_app_password",
    "APP_BROKER_PASSWORD": "broker_app_password",
}
LEGACY_REFERENCES = {
    "APP_DB_ADMIN_PASSWORD_FILE": "db_admin_password",
    "APP_DB_PASSWORD_FILE": "db_app_password",
    "APP_BROKER_PASSWORD_FILE": "broker_app_password",
}
ASSET_PATHS = (
    Path("certs/ca.crt"),
    Path("certs/ca.key"),
    *(Path(f"certs/{service}.{suffix}") for service in SERVICES for suffix in ("crt", "key")),
)


class BootstrapError(RuntimeError):
    """Local assets are incomplete or unsafe to use; no automatic repair occurs."""


def _name(label: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, label)])


def _pem_key(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public_key_bytes(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> bytes:
    public_key = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _general_name(value: str) -> x509.DNSName | x509.IPAddress:
    try:
        return x509.IPAddress(ipaddress.ip_address(value))
    except ValueError:
        return x509.DNSName(value)


def _make_certificates(now: datetime) -> dict[Path, bytes]:
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = _name("Document Platform local development CA")
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    assets = {
        Path("certs/ca.crt"): ca.public_bytes(serialization.Encoding.PEM),
        Path("certs/ca.key"): _pem_key(ca_key),
    }
    for service, names in SERVICES.items():
        key = ec.generate_private_key(ec.SECP256R1())
        certificate = (
            x509.CertificateBuilder()
            .subject_name(_name(service))
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(x509.SubjectAlternativeName([_general_name(n) for n in names]), False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, False, False, False, False),
                True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
            )
            .sign(ca_key, hashes.SHA256())
        )
        assets[Path(f"certs/{service}.crt")] = certificate.public_bytes(serialization.Encoding.PEM)
        assets[Path(f"certs/{service}.key")] = _pem_key(key)
    return assets


def _validate_assets(assets: dict[Path, bytes], now: datetime) -> None:
    try:
        certificates: dict[str, x509.Certificate] = {}
        for label in ("ca", *SERVICES):
            certificate = x509.load_pem_x509_certificate(assets[Path(f"certs/{label}.crt")])
            key = serialization.load_pem_private_key(
                assets[Path(f"certs/{label}.key")], password=None
            )
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise ValueError("unsupported key")
            public_key = certificate.public_key()
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                raise ValueError("unsupported public key")
            if _public_key_bytes(key) != _public_key_bytes(public_key):
                raise ValueError("key mismatch")
            if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc:
                raise ValueError("certificate expired or not yet valid")
            certificates[label] = certificate
        ca = certificates["ca"]
        ca.verify_directly_issued_by(ca)
        ca_constraints = ca.extensions.get_extension_for_class(x509.BasicConstraints)
        if not ca_constraints.critical or ca_constraints.value != x509.BasicConstraints(True, 0):
            raise ValueError("invalid CA constraints")
        if not ca.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
            raise ValueError("invalid CA key usage")
        for service, names in SERVICES.items():
            certificate = certificates[service]
            certificate.verify_directly_issued_by(ca)
            constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints)
            if not constraints.critical or constraints.value.ca:
                raise ValueError("invalid server constraints")
            sans = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            if set(sans) != {_general_name(name) for name in names}:
                raise ValueError("invalid server names")
            eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            if set(eku) != {ExtendedKeyUsageOID.SERVER_AUTH}:
                raise ValueError("invalid server usage")
    except (ValueError, TypeError, KeyError, x509.ExtensionNotFound, InvalidSignature) as exc:
        raise BootstrapError("Local certificate set is invalid; no files were changed.") from exc


def _read_assets(output_dir: Path) -> dict[Path, bytes]:
    for directory in (output_dir, output_dir / "certs"):
        if directory.is_symlink() or not directory.is_dir():
            raise BootstrapError("Local asset directories are incomplete or symbolic links.")
    assets: dict[Path, bytes] = {}
    for relative in ASSET_PATHS:
        file = output_dir / relative
        if file.is_symlink() or not file.is_file():
            raise BootstrapError(
                "Local assets are incomplete; refusing to overwrite or regenerate them."
            )
        assets[relative] = file.read_bytes()
    return assets


def _parse_environment(content: str) -> tuple[list[Binding], dict[str, str | None]]:
    bindings = list(parse_stream(StringIO(content)))
    values: dict[str, str | None] = {}
    for binding in bindings:
        if binding.error:
            raise BootstrapError("The environment file has invalid syntax; no files were changed.")
        if binding.key is not None:
            normalized = binding.key.upper()
            if normalized in values:
                raise BootstrapError(
                    "The environment file has duplicate keys; no files were changed."
                )
            values[normalized] = binding.value
    return bindings, values


def _validate_credentials(values: dict[str, str]) -> None:
    if set(values) != set(ENV_SECRETS) or any(
        len(value) < 32 or not value.strip() or any(char in value for char in "\r\n\0")
        for value in values.values()
    ):
        raise BootstrapError(
            "Environment credentials are missing or invalid; no files were changed."
        )
    if len(set(values.values())) != len(ENV_SECRETS):
        raise BootstrapError("Environment credentials must be distinct; no files were changed.")


def _legacy_credentials(output_dir: Path) -> dict[str, str] | None:
    directory = output_dir / "secrets"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise BootstrapError("Legacy credentials are unsafe to read; no files were changed.")
    if not directory.exists():
        return None
    values: dict[str, str] = {}
    for name, filename in ENV_SECRETS.items():
        path = directory / filename
        if path.is_symlink() or not path.is_file():
            raise BootstrapError("Legacy credential set is incomplete; no files were changed.")
        try:
            values[name] = path.read_text(encoding="utf-8").rstrip("\r\n")
        except UnicodeError:
            raise BootstrapError(
                "Legacy credentials cannot be read; no files were changed."
            ) from None
    _validate_credentials(values)
    return values


def _inline_comment(original: str) -> str:
    """Preserve a trailing dotenv comment when retiring an assignment."""
    quote: str | None = None
    escaped = False
    for index, character in enumerate(original):
        if escaped:
            escaped = False
        elif character == "\\" and quote is not None:
            escaped = True
        elif character in "'\"":
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
        elif character == "#" and quote is None and (index == 0 or original[index - 1].isspace()):
            return original[index:]
    return ""


def _assignment(name: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"{name}='{escaped}'\n"


def _render_environment(
    bindings: list[Binding], credentials: dict[str, str], output_dir: Path, *, new_file: bool
) -> str:
    lines: list[str] = []
    written: set[str] = set()
    configured_tls: set[str] = set()
    tls_paths = {
        "APP_TLS_CA_FILE": output_dir / "certs/ca.crt",
        "APP_API_CERT_FILE": output_dir / "certs/api.crt",
        "APP_API_KEY_FILE": output_dir / "certs/api.key",
    }
    for binding in bindings:
        normalized = binding.key.upper() if binding.key is not None else ""
        if normalized in tls_paths:
            if binding.value is None or not binding.value.strip():
                raise BootstrapError(
                    "Configured TLS paths must not be empty; no files were changed."
                )
            configured_tls.add(normalized)
        if normalized in LEGACY_REFERENCES:
            lines.append(_inline_comment(binding.original.string))
        elif normalized in credentials and not binding.value:
            lines.append(_assignment(normalized, credentials[normalized]))
            lines.append(_inline_comment(binding.original.string))
            written.add(normalized)
        elif new_file and normalized in tls_paths:
            lines.append(_assignment(normalized, tls_paths[normalized].as_posix()))
        else:
            lines.append(binding.original.string)
            if normalized in credentials:
                written.add(normalized)
    content = "".join(lines)
    if content and not content.endswith(("\n", "\r")):
        content += "\n"
    for name, value in credentials.items():
        if name not in written:
            content += _assignment(name, value)
    for name, path in tls_paths.items():
        if name not in configured_tls:
            content += _assignment(name, path.as_posix())
    return content


def _write_environment(path: Path, content: bytes, expected: bytes | None) -> None:
    """Publish a private file atomically, rejecting a concurrent edit before replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".env.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            temporary.chmod(0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise BootstrapError("Environment file changed during preparation; retry safely.")
        current = path.read_bytes() if path.exists() else None
        if current != expected:
            raise BootstrapError(
                "Environment file changed during preparation; no replacement made."
            )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def bootstrap(
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    env_file: Path | None = None,
    check_only: bool = False,
) -> bool:
    """Prepare TLS plus literal dotenv credentials, preserving existing identities.

    Legacy secret files are copied into dotenv after validation and retained as
    ignored backups. Existing certificates or populated credentials never rotate.
    A partial credential set or a conflict is rejected before any file changes.
    """
    output_dir = Path(output_dir).absolute()
    env_file = Path(env_file).absolute() if env_file is not None else output_dir.parent / ".env"
    name = env_file.name
    if (
        not (name == ".env" or name.startswith(".env."))
        or name.rstrip(" .").casefold() == ".env.example"
        or name != name.rstrip(" .")
    ):
        raise BootstrapError("Environment destination must be a private .env file, not a template.")
    now = datetime.now(UTC)
    if output_dir.is_symlink() or env_file.is_symlink():
        raise BootstrapError("Local asset paths must not be symbolic links.")
    exists = output_dir.exists()
    if exists:
        assets = _read_assets(output_dir)
        _validate_assets(assets, now)
    elif check_only:
        raise BootstrapError("Local assets do not exist; run bootstrap first.")
    else:
        assets = _make_certificates(now)
        _validate_assets(assets, now)

    expected = env_file.read_bytes() if env_file.exists() else None
    try:
        if expected is not None:
            source = expected.decode("utf-8")
        else:
            template = Path(__file__).resolve().parents[1] / ".env.example"
            source = template.read_text(encoding="utf-8")
        bindings, values = _parse_environment(source)
    except UnicodeError:
        raise BootstrapError(
            "The environment file must use UTF-8; no files were changed."
        ) from None

    legacy = _legacy_credentials(output_dir)
    for reference, filename in LEGACY_REFERENCES.items():
        value = values.get(reference)
        if (
            value is not None
            and (env_file.parent / value).absolute()
            != (output_dir / "secrets" / filename).absolute()
        ):
            raise BootstrapError("Legacy credential paths differ; manual migration is required.")
    credentials = {
        name: value
        for name in ENV_SECRETS
        if (value := values.get(name)) is not None and value != ""
    }
    if credentials:
        _validate_credentials(credentials)
        if legacy is not None and credentials != legacy:
            raise BootstrapError(
                "Environment and legacy credentials conflict; no files were changed."
            )
    elif legacy is not None:
        credentials = legacy
    elif exists or any(reference in values for reference in LEGACY_REFERENCES):
        raise BootstrapError("Environment credentials are missing; no files were changed.")
    else:
        credentials = {name: secrets.token_urlsafe(48) for name in ENV_SECRETS}
    _validate_credentials(credentials)

    content = _render_environment(bindings, credentials, output_dir, new_file=expected is None)
    _, rendered = _parse_environment(content)
    if any(rendered.get(name) != value for name, value in credentials.items()):
        raise BootstrapError("Environment credentials could not be represented safely.")
    needs_env = expected != content.encode("utf-8")
    if check_only:
        if any(values.get(name) != value for name, value in credentials.items()):
            raise BootstrapError("Credentials require environment migration; run bootstrap first.")
        if any(
            not values.get(name)
            for name in ("APP_TLS_CA_FILE", "APP_API_CERT_FILE", "APP_API_KEY_FILE")
        ):
            raise BootstrapError("TLS paths require environment preparation; run bootstrap first.")
        return False

    if not exists:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(mode=0o700)
        (output_dir / "certs").mkdir(mode=0o700)
        for relative, asset_bytes in assets.items():
            target = output_dir / relative
            with target.open("xb") as handle:
                handle.write(asset_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            target.chmod(0o644 if relative.suffix == ".crt" else 0o600)
        _validate_assets(_read_assets(output_dir), now)
    if needs_env:
        _write_environment(env_file, content.encode("utf-8"), expected)
    return not exists or needs_env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, help="Defaults to the parent of output-dir/.env.")
    parser.add_argument(
        "--check-only", action="store_true", help="Validate; do not create or change files."
    )
    args = parser.parse_args()
    try:
        created = bootstrap(args.output_dir, env_file=args.env_file, check_only=args.check_only)
    except BootstrapError as exc:
        print(f"Bootstrap refused: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("Bootstrap refused: local assets could not be accessed safely.", file=sys.stderr)
        return 1
    print(
        "Local development TLS assets and environment prepared."
        if created
        else "Local development assets verified; unchanged."
    )
    print(
        "No OS trust changes were made. Files remain subject to host ACLs and storage encryption."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
