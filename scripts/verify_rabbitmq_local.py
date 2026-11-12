"""Verify real TLS/auth/permission failures without printing secrets or consuming messages."""

from __future__ import annotations

import json
import socket
import ssl
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from amqp.exceptions import AccessRefused
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pydantic import SecretStr

from document_platform.config import Settings
from document_platform.infrastructure.messaging.connection import broker_connection, check_broker
from scripts.prepare_rabbitmq_local import assert_operator


def certificate_failure(error: BaseException) -> bool:
    """Recognize certificate verification specifically, not a general network failure."""
    seen: set[int] = set()
    while id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ssl.SSLCertVerificationError):
            return True
        nested = error.__cause__ or error.__context__
        if nested is None:
            break
        error = nested
    return False


def _foreign_ca(path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic untrusted CA")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def verify(settings: Settings) -> dict[str, bool]:
    """Verify the live broker baseline before testing deliberately invalid clients."""
    if settings.broker_host != "localhost" or settings.broker_port != 5671:
        raise ValueError("This verification is restricted to the configured local broker")
    check_broker(settings)
    results = {"baseline_tls": True}
    try:
        check_broker(
            settings.model_copy(update={"broker_password": SecretStr("wrong-" + "x" * 64)})
        )
    except AccessRefused:
        results["incorrect_password_rejected"] = True
    else:
        raise RuntimeError("Incorrect password was unexpectedly accepted")
    with tempfile.TemporaryDirectory(prefix="rabbitmq-negative-") as directory:
        path = Path(directory) / "foreign-ca.crt"
        _foreign_ca(path)
        try:
            check_broker(settings.model_copy(update={"tls_ca_file": path}))
        except Exception as exc:
            if not certificate_failure(exc):
                raise RuntimeError("Untrusted CA failed for an unexpected reason") from None
            results["untrusted_ca_rejected"] = True
        else:
            raise RuntimeError("Untrusted CA was unexpectedly accepted")
    with broker_connection(settings) as connection:
        connection.ssl = dict(connection.ssl) | {"server_hostname": "wrong.invalid"}
        try:
            connection.connect()
        except Exception as exc:
            if not certificate_failure(exc):
                raise RuntimeError("Hostname test failed for an unexpected reason") from None
            results["incorrect_hostname_rejected"] = True
        else:
            raise RuntimeError("Incorrect hostname was unexpectedly accepted")
    with socket.socket() as probe:
        probe.settimeout(2)
        if probe.connect_ex(("127.0.0.1", 5672)) == 0:
            raise RuntimeError("Plaintext AMQP is still listening")
    results["plaintext_listener_disabled"] = True
    with broker_connection(settings) as connection:
        connection.connect()
        try:
            connection.channel().queue_declare(queue="document_platform.forbidden", durable=True)
        except AccessRefused:
            results["queue_permissions_restricted"] = True
        else:
            raise RuntimeError("Account unexpectedly has permission to create an unrelated queue")
    return results


def main() -> int:
    try:
        assert_operator()
        results = verify(Settings())
    except Exception:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "message": "Live broker security check failed; no credentials were disclosed.",
                }
            )
        )
        return 1
    print(json.dumps({"status": "passed", "checks": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
