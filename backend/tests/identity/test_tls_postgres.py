"""Negative handshakes use no real password and verify the native PostgreSQL listener."""

import socket
import ssl
import struct

import pytest


def test_real_postgres_rejects_plaintext_before_password(pg_environment: tuple) -> None:
    settings, _, _ = pg_environment
    parameters = b"user\0document_app\0database\0" + settings.db_name.encode() + b"\0\0"
    payload = struct.pack("!I", 196608) + parameters
    with socket.create_connection((settings.db_host, settings.db_port), timeout=3) as sock:
        sock.sendall(struct.pack("!I", len(payload) + 4) + payload)
        # A server error, not the authentication/password challenge (R).
        assert sock.recv(1) == b"E"


def test_real_postgres_rejects_wrong_server_name(pg_environment: tuple) -> None:
    settings, _, _ = pg_environment
    context = ssl.create_default_context(cafile=str(settings.tls_ca_file))
    with socket.create_connection((settings.db_host, settings.db_port), timeout=3) as sock:
        sock.sendall(struct.pack("!II", 8, 80877103))
        assert sock.recv(1) == b"S"
        with pytest.raises(ssl.SSLCertVerificationError, match="Hostname mismatch"):
            context.wrap_socket(sock, server_hostname="wrong-name.invalid")


def test_real_postgres_certificate_requires_its_ca(pg_environment: tuple) -> None:
    settings, _, _ = pg_environment
    context = ssl.create_default_context()
    with socket.create_connection((settings.db_host, settings.db_port), timeout=3) as sock:
        sock.sendall(struct.pack("!II", 8, 80877103))
        assert sock.recv(1) == b"S"
        with pytest.raises(ssl.SSLCertVerificationError):
            context.wrap_socket(sock, server_hostname=settings.db_host)
