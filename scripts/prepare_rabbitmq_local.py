"""Prepare local RabbitMQ TLS and hashed definitions without rotating existing secrets."""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import ipaddress
import json
import os
import secrets
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from dotenv.parser import parse_stream

from document_platform.config import Settings

MARKER = "# document-platform local RabbitMQ TLS configuration"
RESOURCE_PATTERN = r"^document_platform[.]integration$"


def assert_operator() -> None:
    """Refuse to create user assets under the Codex sandbox Windows identities."""
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(257)
        length = ctypes.c_ulong(len(buffer))
        if not ctypes.windll.advapi32.GetUserNameW(buffer, ctypes.byref(length)):
            raise RuntimeError("Cannot determine the Windows account")
        if "codex" in buffer.value.casefold():
            raise RuntimeError("Run this command as your own Windows account, outside the sandbox")


def render_config(service_dir: Path) -> str:
    """Disable plain AMQP and expose the TLS listener only on IPv4 loopback."""
    location = service_dir.absolute().as_posix()
    if any(character in location for character in "\r\n#"):
        raise ValueError("Unsupported service path")
    return f"""{MARKER}
listeners.tcp = none
listeners.ssl.1 = 127.0.0.1:5671
ssl_options.cacertfile = {location}/ca.crt
ssl_options.certfile = {location}/server.crt
ssl_options.keyfile = {location}/server.key
ssl_options.verify = verify_peer
ssl_options.fail_if_no_peer_cert = false
ssl_options.versions.1 = tlsv1.3
ssl_options.versions.2 = tlsv1.2
definitions.import_backend = local_filesystem
definitions.local.path = {location}/definitions.json
definitions.skip_if_unchanged = true
log.console.level = warning
"""


def _credentials_match(encoded: str, password: str) -> bool:
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except ValueError:
        return False
    return len(decoded) == 36 and secrets.compare_digest(
        decoded[4:], hashlib.sha256(decoded[:4] + password.encode()).digest()
    )


def definitions(settings: Settings, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a restricted user definition; preserve its salted password hash on rerun."""
    password = settings.broker_password.get_secret_value()
    salt = secrets.token_bytes(4)
    encoded = base64.b64encode(salt + hashlib.sha256(salt + password.encode()).digest()).decode()
    result: dict[str, Any] = {
        "users": [
            {
                "name": settings.broker_user,
                "password_hash": encoded,
                "hashing_algorithm": "rabbit_password_hashing_sha256",
                "tags": [],
            }
        ],
        "vhosts": [{"name": settings.broker_vhost}],
        "permissions": [
            {
                "user": settings.broker_user,
                "vhost": settings.broker_vhost,
                "configure": RESOURCE_PATTERN,
                "write": RESOURCE_PATTERN,
                "read": RESOURCE_PATTERN,
            }
        ],
    }
    if existing is not None:
        users = existing.get("users", [])
        if len(users) != 1 or not _credentials_match(users[0].get("password_hash", ""), password):
            raise ValueError(
                "Existing definitions conflict; explicit credential rotation is required"
            )
        result["users"][0]["password_hash"] = users[0]["password_hash"]
        if existing != result:
            raise ValueError("Existing broker permissions differ; review the configuration")
        return existing
    return result


def _server_assets(root: Path, settings: Settings) -> tuple[bytes, bytes]:
    ca = x509.load_pem_x509_certificate(settings.tls_ca_file.read_bytes())
    ca_key = serialization.load_pem_private_key((root / ".local/certs/ca.key").read_bytes(), None)
    if not isinstance(ca_key, ec.EllipticCurvePrivateKey):
        raise ValueError("Unsupported development CA key")
    if ca_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ) != ca.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ):
        raise ValueError("Development CA certificate/key mismatch")
    now = datetime.now(UTC)
    if not ca.not_valid_before_utc <= now < ca.not_valid_after_utc - timedelta(days=1):
        raise ValueError("Development CA needs renewal")
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(min(now + timedelta(days=90), ca.not_valid_after_utc))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("rabbitmq"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, False, False, False, False), True
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM), key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def prepare(root: Path, service_dir: Path, settings: Settings) -> Path:
    """Stage only this feature's files; do not install configuration or restart services."""
    assert_operator()
    output = root / ".local/rabbitmq"
    if output.is_symlink():
        raise ValueError("Unsafe output directory")
    for name in ("ca.crt", "server.crt", "server.key", "definitions.json", "rabbitmq.conf"):
        target = output / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError("Unsafe existing broker asset")
    cert_path, key_path = output / "server.crt", output / "server.key"
    if cert_path.exists() != key_path.exists():
        raise ValueError("Incomplete broker TLS assets; no automatic renewal")
    if cert_path.exists():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
        certificate.verify_directly_issued_by(
            x509.load_pem_x509_certificate(settings.tls_ca_file.read_bytes())
        )
        if certificate.not_valid_after_utc <= datetime.now(UTC):
            raise ValueError("Broker certificate expired; explicit renewal is required")
        if "localhost" not in certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.DNSName):
            raise ValueError("Broker certificate does not cover localhost")
        cert, key = cert_path.read_bytes(), key_path.read_bytes()
    else:
        cert, key = _server_assets(root, settings)
    definition_path = output / "definitions.json"
    existing = json.loads(definition_path.read_text()) if definition_path.exists() else None
    content = json.dumps(definitions(settings, existing), indent=2) + "\n"
    output.mkdir(parents=True, exist_ok=True)
    for path, data in (
        (cert_path, cert),
        (key_path, key),
        (output / "ca.crt", settings.tls_ca_file.read_bytes()),
        (definition_path, content.encode()),
        (output / "rabbitmq.conf", render_config(service_dir).encode()),
    ):
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
    return output


def configure_local_environment(root: Path) -> None:
    """Change only broker host/port and atomically preserve all dotenv secrets."""
    from io import StringIO

    from scripts.bootstrap_local import _write_environment

    path = root / ".env"
    before = path.read_bytes()
    lines = []
    updates = {"APP_BROKER_HOST": "localhost", "APP_BROKER_PORT": "5671"}
    seen: set[str] = set()
    for binding in parse_stream(StringIO(before.decode("utf-8"))):
        if binding.error:
            raise ValueError("Invalid dotenv syntax")
        name = binding.key.upper() if binding.key else ""
        if name in updates:
            if name in seen:
                raise ValueError("Duplicate broker setting")
            seen.add(name)
            lines.append(f"{name}='{updates[name]}'\n")
        else:
            lines.append(binding.original.string)
    content = "".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"
    for name, value in updates.items():
        if name not in seen:
            content += f"{name}='{value}'\n"
    if content.encode() != before:
        _write_environment(path, content.encode(), before)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", type=Path)
    args = parser.parse_args()
    try:
        assert_operator()
        if args.service_dir is None:
            if os.name != "nt":
                raise ValueError("Specify --service-dir on non-Windows hosts")
            service_dir = Path(os.environ["APPDATA"]) / "RabbitMQ/document-platform"
        else:
            service_dir = args.service_dir
        root = Path(__file__).resolve().parents[1]
        prepare(root, service_dir, Settings())
        configure_local_environment(root)
    except Exception:
        print("Preparation failed; check the operator account, TLS assets and local configuration.")
        return 1
    print("RabbitMQ TLS configuration staged. Secrets and signing key were not printed or rotated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
