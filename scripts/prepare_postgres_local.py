"""Stage a localhost PostgreSQL TLS certificate and a restrictive local configuration."""

import ipaddress
import json
import os
import ssl
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from dotenv.parser import parse_stream

from scripts.bootstrap_local import _write_environment
from scripts.prepare_rabbitmq_local import assert_operator


def prepare() -> None:
    assert_operator()
    root = Path(__file__).resolve().parents[1]
    stage = root / ".local/postgres"
    service = Path(os.environ["PROGRAMDATA"]) / "DocumentPlatform/PostgreSQL"
    stage.mkdir(parents=True, exist_ok=True)
    ca = x509.load_pem_x509_certificate((root / ".local/certs/ca.crt").read_bytes())
    key = serialization.load_pem_private_key((root / ".local/certs/ca.key").read_bytes(), None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise TypeError("Unsupported CA")
    certfile, keyfile = stage / "server.crt", stage / "server.key"
    if certfile.exists() != keyfile.exists():
        raise ValueError("Partial PostgreSQL TLS identity")
    if not certfile.exists():
        leafkey = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        leaf = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
            .issuer_name(ca.subject)
            .public_key(leafkey.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(min(now + timedelta(days=90), ca.not_valid_after_utc))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.DNSName("postgres"),
                        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                        x509.IPAddress(ipaddress.ip_address("::1")),
                    ]
                ),
                False,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, False, False, False, False), True
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leafkey.public_key()), False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), False
            )
            .sign(key, hashes.SHA256())
        )
        certfile.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        keyfile.write_bytes(
            leafkey.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    leaf = x509.load_pem_x509_certificate(certfile.read_bytes())
    leaf.verify_directly_issued_by(ca)
    if leaf.not_valid_after_utc <= datetime.now(UTC):
        raise ValueError("PostgreSQL certificate requires renewal")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)
    (stage / "ca.crt").write_bytes((root / ".local/certs/ca.crt").read_bytes())
    prefix = service.as_posix()
    config = f"""# document-platform PostgreSQL localhost TLS
listen_addresses = 'localhost'
ssl = on
ssl_cert_file = '{prefix}/server.crt'
ssl_key_file = '{prefix}/server.key'
ssl_ca_file = '{prefix}/ca.crt'
ssl_min_protocol_version = 'TLSv1.2'
password_encryption = 'scram-sha-256'
hba_file = '{prefix}/pg_hba.conf'
"""
    hba = """# document-platform PostgreSQL network access: TLS and loopback only
hostnossl all all 0.0.0.0/0 reject
hostnossl all all ::/0 reject
hostssl all postgres 127.0.0.1/32 scram-sha-256
hostssl all postgres ::1/128 scram-sha-256
hostssl /^document_platform(_test_[a-f0-9]+)?$ document_app 127.0.0.1/32 scram-sha-256
hostssl /^document_platform(_test_[a-f0-9]+)?$ document_app ::1/128 scram-sha-256
host all all 0.0.0.0/0 reject
host all all ::/0 reject
"""
    (stage / "document-platform.conf").write_text(config, encoding="utf-8", newline="\n")
    (stage / "pg_hba.conf").write_text(hba, encoding="utf-8", newline="\n")
    # Save only non-secret status for the operator.
    (stage / "prepared.json").write_text(
        json.dumps({"service_directory": str(service), "tls": True}), encoding="utf-8"
    )
    path = root / ".env"
    before = path.read_bytes()
    updates = {"APP_DB_HOST": "localhost", "APP_DB_PORT": "5432", "APP_DB_ADMIN_USER": "postgres"}
    parts = []
    seen = set()
    for item in parse_stream(StringIO(before.decode("utf-8"))):
        if item.error:
            raise ValueError("Invalid dotenv")
        name = item.key.upper() if item.key else ""
        if name in updates:
            parts.append(f"{name}='{updates[name]}'\n")
            seen.add(name)
        else:
            parts.append(item.original.string)
    text = "".join(parts)
    if text and not text.endswith("\n"):
        text += "\n"
    for name, value in updates.items():
        if name not in seen:
            text += f"{name}='{value}'\n"
    if text.encode() != before:
        _write_environment(path, text.encode(), before)


if __name__ == "__main__":
    try:
        prepare()
    except Exception:  # noqa: BLE001 - suppress potentially sensitive operational details
        raise SystemExit(
            "PostgreSQL TLS preparation failed; check paths and certificates."
        ) from None
    print("PostgreSQL TLS assets staged as the current operator; credentials unchanged.")
